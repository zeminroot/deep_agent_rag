#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   deep_agent_rag.py
@Author  :   zemin
@Desc    :   让模型像人类研究员一样主动翻页查找文档资料，react、deepsearch模式
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config import get_settings
import json
import asyncio
from typing import List, Dict, Any, Optional
from loguru import logger
from openai import AsyncOpenAI
import json
from loguru import logger
from knowledge_retrieval.tool_manager import ToolManager
from knowledge_retrieval import ai_tools
from typing import Optional, Dict, List, Any



class DeepAgentRag:
    def __init__(self):
        self.settings = get_settings()
        self.openai_client = AsyncOpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
        )
        self.model = self.settings.llm_model
        self.MAX_TOOL_STEPS = 10
        self.tool_manager = ToolManager()
        self.system_prompt = ai_tools.load_system_prompt()
        self._register_all_tools()

    def _register_all_tools(self):
        """
        自动注册ai_tools模块中的所有工具
        """
        try:
            self.tool_manager.register_from_module(ai_tools)
            logger.success(f"工具注册完成，可用工具：{list(self.tool_manager.tool_registry.keys())}")
        except Exception as e:
            logger.error(f"工具注册失败：{str(e)}")
            raise

    async def get_tools_schema(self) -> List[Dict]:
        """
        获取工具描述
        """
        return await self.tool_manager.get_openai_tools()

    async def _execute_tools(self, tool_calls: List[Dict], request_id: str = None) -> List[Dict]:
        """
        批量执行多个工具调用
        """
        tool_results = []
        for call in tool_calls:
            try:
                tool_args = call["arguments"]
                # 传递 request_id 到工具参数
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

    async def _parse_tool_calls(self, response) -> Optional[List[Dict]]:
        """
        解析大模型返回的工具调用
        """
        if not response.choices:
            return None
        message = response.choices[0].message
        tool_calls = message.tool_calls
        if not tool_calls:
            return None

        # 解析所有工具调用
        parsed_calls = []
        for tool_call in tool_calls:
            try:
                parsed_calls.append({
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments)
                })
            except json.JSONDecodeError:
                logger.error(f"工具参数解析失败：{tool_call.function.arguments}")
        return parsed_calls if parsed_calls else None

    async def _process_single_query(self, query: str, request_id: str = None) -> str:
        """
        处理单个query，循环调用工具，直到返回答案/超过10轮
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query}
        ]
        step = 0

        while step < self.MAX_TOOL_STEPS:
            step += 1
            logger.info(f"query：{query[:20]}... 第 {step}/{self.MAX_TOOL_STEPS} 轮工具调用")

            try:
                response = await self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=await self.get_tools_schema(),
                    tool_choice="auto"
                )
            except Exception as e:
                err = f"大模型调用失败：{str(e)}"
                logger.error(err)
                return err

            # 解析工具调用
            tool_calls = await self._parse_tool_calls(response)
            assistant_msg = response.choices[0].message

            # 无工具调用，返回最终答案
            if not tool_calls:
                answer = assistant_msg.content or "无有效回答"
                return answer

            # 有工具调用，执行工具并追加上下文
            messages.append(assistant_msg)
            tool_results = await self._execute_tools(tool_calls, request_id)
            messages.extend(tool_results)

        logger.warning(f"查询【{query}】超过{self.MAX_TOOL_STEPS}轮，强制结束")
        return "请基于你自身知识回答。"

    async def run_batch(self, query_list: List[str], request_id: str = None) -> List[str]:
        """
        批量处理多个query
        返回答案列表，顺序一一对应

        Args:
            query_list: 查询列表
            request_id: 请求ID，用于追踪检索元数据
        """
        if not query_list:
            logger.warning("query_list 为空")
            return []

        logger.info(f"开始批量处理 {len(query_list)} 个查询，request_id: {request_id}")

        answer_list = []

        for idx, query in enumerate(query_list):
            logger.info(f"\n--- 处理第 {idx+1} 个问题：{query} ---")
            answer = await self._process_single_query(query, request_id)
            logger.info(f"\n得到答案：{answer}")

            answer_list.append(answer)

        logger.success("批量处理完成！")
        return answer_list


if __name__ == "__main__":
    import asyncio

    async def test():
        agent = DeepAgentRag()
        
        await agent.run_batch(query_list=["什么是特里芬难题"], request_id="1111")
        
    asyncio.run(test())
    
    

        
    