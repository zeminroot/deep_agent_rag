#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   main_agent.py
@Author  :   zemin
@Desc    :   主智能体，将deep_agent_rag作为子智能体，协调回答问题
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config import get_settings
import pickle
import json
import uuid
from typing import List, Dict, Optional, Any
from loguru import logger
from openai import AsyncOpenAI
from redis.asyncio import Redis as AsyncRedis
from utils.tool_manager import ToolManager
from main_agent import main_agent_tools as main_tools
from utils.prompt_loader import load_prompt
from utils.json_utils import fix_json_string
from datetime import datetime


class MainAgent:
    def __init__(self):
        self.settings = get_settings()
        self.openai_client = AsyncOpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
        )
        self.model = self.settings.llm_model
        self.MAX_TOOL_STEPS = 1
        self.MAX_HISTORY_ROUNDS = 20  # 滑动窗口保留最近20轮qa

        # 初始化 Redis 客户端
        self.redis_client = AsyncRedis(
            host=self.settings.redis_host,
            port=self.settings.redis_port,
            db=self.settings.redis_db,
            password=self.settings.redis_password,
            decode_responses=False  
        )

        self.tool_manager = ToolManager()

        # 注入Agent工具
        self._register_all_tools()


    def _register_all_tools(self):
        """
        自动注册 main_agent_tools 模块中的所有工具
        """
        try:
            self.tool_manager.register_from_module(main_tools)
            logger.success(f"工具注册完成，可用工具：{list(self.tool_manager.tool_registry.keys())}")
        except Exception as e:
            logger.error(f"工具注册失败：{str(e)}")
            raise


    async def _execute_tools(self, tool_calls: List[Dict], request_id: str = None) -> List[Dict]:
        """
        批量执行多个工具调用。tool_calls: 工具调用列表。request_id: 请求ID，记录检索过程中获取的chunks
        """
        tool_results = []
        for call in tool_calls:
            try:
                tool_args = call["arguments"]
                if request_id:
                    tool_args["request_id"] = request_id

                result = await self.tool_manager.execute_tool(
                    tool_name=call["name"],
                    tool_args=tool_args
                )
                # 构造工具结果
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": str(result) if result else "工具执行成功，无返回结果"
                })
            except Exception as e:
                err_msg = f"工具【{call['name']}】执行失败：{str(e)}"
                logger.error(err_msg)
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": err_msg
                })
        return tool_results


    async def _get_retrieval_chunks(self, request_id: str) -> List[Dict]:
        """
        获取请求的所有检索 chunk 信息。request_id: 请求ID
        返回chunk 列表，按时间排序
        """
        retrieval_key = f"retrieval:{request_id}"
        try:
            all_metadata = await self.redis_client.hgetall(retrieval_key)
            if not all_metadata:
                return []

            # 按时间戳排序
            sorted_items = sorted(all_metadata.items(), key=lambda x: json.loads(x[1])["timestamp"])

            chunks = []
            for _, metadata_json in sorted_items:
                metadata = json.loads(metadata_json)
                chunks.extend(metadata.get("records", []))

            return chunks
        except Exception as e:
            logger.error(f"获取检索chunk信息失败: {e}")
            return []


    async def _load_conversation_history(self, user_id: str, session_id: str) -> List[Dict]:
        """
        从 Redis 加载对话历史
        返回对话历史消息列表
        """
        session_key = f"chat:{user_id}:{session_id}"
        try:
            history_data = await self.redis_client.get(session_key)
            if history_data:
                history = pickle.loads(history_data)
                logger.info(f"加载对话历史: {len(history)} 条消息")
                return history
            return []
        except Exception as e:
            logger.error(f"加载对话历史失败: {e}")
            return []


    async def _save_conversation_history(
        self,
        user_id: str,
        session_id: str,
        messages: List[Dict]
    ) -> bool:
        """
        保存对话历史到 Redis
        返回是否保存成功标志
        """
        session_key = f"chat:{user_id}:{session_id}"
        try:
            max_messages = self.MAX_HISTORY_ROUNDS * 2 + 1
            messages_to_save = messages[-max_messages:] if len(messages) > max_messages else messages

            await self.redis_client.set(
                session_key,
                pickle.dumps(messages_to_save),
                ex=self.settings.redis_state_ttl
            )
            logger.debug(f"保存对话历史: {len(messages_to_save)} 条消息")
            return True
        except Exception as e:
            logger.error(f"保存对话历史失败: {e}")
            return False


    async def _parse_tool_calls(self, response) -> Optional[List[Dict]]:
        """
        解析大模型返回的工具调用
        """
        message = response.choices[0].message if response.choices else None
        if not message or not message.tool_calls:
            return None

        parsed_calls = []
        for tool_call in message.tool_calls:
            try:
                parsed_calls.append({
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments)
                })
            except json.JSONDecodeError:
                # 尝试修复常见的 JSON 格式问题
                raw_args = tool_call.function.arguments
                logger.warning(f"工具参数 JSON 解析失败，尝试修复: {raw_args[:200]}")
                try:
                    fixed_args = fix_json_string(raw_args)
                    parsed_calls.append({
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": json.loads(fixed_args)
                    })
                except Exception as e2:
                    logger.error(f"工具参数解析失败: {raw_args}, 修复后仍失败: {e2}")
        return parsed_calls or None


    async def process_single_query(
        self,
        user_id: str,
        session_id: str,
        query: str,
        request_id: str = None
    ) -> Dict[str, Any]:
        """
        用户每次对话交互，返回回答结果，返回格式：
            {
                "request_id": "请求ID",
                "answer": "回答结果",
                "retrieved_chunks": [
                    {"file_id": 123, "chunk_index": 10},
                    {"file_id": 123, "page_index": 1}
                ]
            }
        """
        if request_id is None:
            request_id = uuid.uuid4().hex

        logger.info(f"请求ID: {request_id} | 用户: {user_id} | 会话: {session_id} \n问题: {query}")

        # 加载对话历史
        history_messages = await self._load_conversation_history(user_id, session_id)

        # 构建消息列表
        if not history_messages:
            # 首次对话，加载系统提示词
            current_time = datetime.now().strftime("%Y年%m月%d日")
            system_prompt = load_prompt(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts/main_agent_system_prompt.md'),
                current_time=current_time
            )
            messages = [{"role": "system", "content": system_prompt}]
        else:
            messages = []
            
        messages.extend(history_messages)
        messages.append({"role": "user", "content": query})

        step = 0
        assistant_reply = None

        while step < self.MAX_TOOL_STEPS:
            step += 1

            try:
                response = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=await self.tool_manager.get_openai_tools(),
                    # tool_choice="auto",  # 大模型自动选择是否检索内部知识库
                    tool_choice={"type": "function", "function": {"name": "knowledge_retrieval_tool"}}  # 强制大模型检索内部知识库
                )
            except Exception as e:
                err = f"大模型调用失败：{str(e)}"
                logger.error(f"请求ID: {request_id} | {err}")
                return {
                    "request_id": request_id,
                    "answer": err,
                    "retrieved_chunks": []
                }

            # 解析工具调用
            tool_calls = await self._parse_tool_calls(response)
            assistant_msg = response.choices[0].message

            # 大模型返回不是工具调用，返回最终答案
            if not tool_calls:
                assistant_reply = assistant_msg.content or "无有效回答"
                messages.append({"role": "assistant", "content": assistant_reply})
                break
            else:
                logger.info(f"请求ID: {request_id} | 第 {step}/{self.MAX_TOOL_STEPS} 轮工具调用")

            # 有工具调用: 追加上下文、执行工具、将工具结果追加到上下文
            messages.append(assistant_msg)
            tool_results = await self._execute_tools(tool_calls, request_id)
            messages.extend(tool_results)
        else:
            # 本次提问超过最大工具调用轮次，让大模型基于已有工具结果直接回答
            logger.warning(f"请求ID: {request_id} | 超过{self.MAX_TOOL_STEPS}轮循环工具调用，让大模型基于已有结果直接回答")
            try:
                response = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=await self.tool_manager.get_openai_tools(),
                    tool_choice="none"  # 强制禁止调用工具
                )
                assistant_reply = response.choices[0].message.content or "无有效回答"
                messages.append({"role": "assistant", "content": assistant_reply})
            except Exception as e:
                err = f"大模型调用失败：{str(e)}"
                logger.error(f"请求ID: {request_id} | {err}")
                assistant_reply = "工具调用轮次超过限制，且生成回答时发生错误。"
                messages.append({"role": "assistant", "content": assistant_reply})

        # 保存对话历史到redis
        await self._save_conversation_history(user_id, session_id, messages)

        # 从redis中拉取本次query过程检索到的 chunk 信息
        retrieved_chunks = await self._get_retrieval_chunks(request_id)

        logger.info(f"请求ID: {request_id} | 回答: {assistant_reply[:50]}...")

        return {
            "request_id": request_id,
            "answer": assistant_reply,
            "retrieved_chunks": retrieved_chunks
        }



if __name__ == "__main__":
    import asyncio

    async def test():
        agent = MainAgent()
        user_id = "test_user3"
        session_id = "test_session3"
        queries = [
            "查阅知识库回答什么是特里芬难题",
            "有解决途径吗"
        ]
        print("=" * 60)

        for idx, query in enumerate(queries):
            print(f"\n--- 第 {idx+1} 轮对话 ---")
            print(f"问题: {query}")

            answer = await agent.process_single_query(
                user_id=user_id,
                session_id=session_id,
                query=query
            )
            print(f"回答: {answer}\n")


    asyncio.run(test())