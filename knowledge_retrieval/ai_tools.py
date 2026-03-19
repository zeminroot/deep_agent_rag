#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   ai_tools.py
@Author  :   zemin
@Desc    :   Agent用到的工具
'''
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from knowledge_retrieval.tool_manager import tool
from knowledge_retrieval.retrieval_rerank_expand import RetrievalRerankExpand
from knowledge_retrieval.page_content_search import PageContentSearch
from urllib.parse import unquote
from loguru import logger
from redis.asyncio import Redis as AsyncRedis
from config.config import get_settings
import json
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional


# 定义全局 Redis 客户端
_redis_client: Optional[AsyncRedis] = None
# 定义全局锁
_redis_lock = asyncio.Lock()

async def get_redis_client() -> AsyncRedis:
    """
    获取 Redis 客户端单例
    使用双重检查锁定模式防止并发创建多个连接
    """
    global _redis_client
    if _redis_client is None:  
        async with _redis_lock:  # 获取锁
            if _redis_client is None:  
                settings = get_settings()
                _redis_client = AsyncRedis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    password=settings.redis_password,
                    decode_responses=True
                )
    return _redis_client


def load_system_prompt() -> str:
    """
    从文件加载系统提示词
    """
    prompt_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "prompts",
        "deep_agent_rag_system_prompt.md"
    )

    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"系统提示词文件未找到: {prompt_file}")
        return "你是一个专业的知识检索助手。借助工具像人类研究员一样主动翻页查找文档资料。"
    except Exception as e:
        logger.error(f"加载系统提示词失败: {e}")
        return "你是一个专业的知识检索助手。借助工具像人类研究员一样主动翻页查找文档资料。"


def get_oss_original_filename(oss_url):
    """
    从OSS地址提取原始文件名
    oss_url: 阿里云OSS文件完整URL
    返回: 解码后的原始文件名
    """
    file_part = oss_url.rsplit('/', 1)[-1]
    encoded_filename = file_part.split('-', 1)[-1]
    original_filename = unquote(encoded_filename)
    return original_filename


async def _save_retrieval_record(
    request_id: str,
    tool_name: str,
    records: List[Dict],
    tool_args: Dict = None
) -> bool:
    """
    保存检索记录到 Redis

    Args:
        request_id: 请求 ID
        tool_name: 工具名称：retrieve_chunk 或 get_page_content
        records: 检索记录列表，如 [{"file_id": 123, "page_index": 1}, ...] 或 [{"file_id": 123, "chunk_index": 5}, ...]
        tool_args: 工具调用参数

    Returns:
        是否保存成功
    """
    if not request_id or not records:
        return False

    try:
        redis_client = await get_redis_client()
        settings = get_settings()

        call_id = f"{tool_name}_{uuid.uuid4().hex[:8]}"
        retrieval_key = f"retrieval:{request_id}"

        metadata = {
            "tool_name": tool_name,
            "timestamp": datetime.now().isoformat(),
            "tool_args": tool_args or {},
            "records": records
        }

        await redis_client.hset(
            retrieval_key,
            call_id,
            json.dumps(metadata, ensure_ascii=False)
        )
        await redis_client.expire(retrieval_key, settings.redis_state_ttl)

        logger.info(f"保存检索记录: request_id={request_id}, tool={tool_name}, records={len(records)}")
        return True
    except Exception as e:
        logger.error(f"保存检索记录失败: {e}")
        return False


# 实例化检索扩展重排服务
retriever = RetrievalRerankExpand()
# 实例化页面内容搜索服务
page_content_searcher = PageContentSearch()


@tool(
    name="retrieve_chunk",
    description="从知识库中检索相关的文本块。召回top10相关文本片段",
    properties={
        "query": {"type": "string", "description": "检索查询文本"},
        "request_id": {"type": "string", "description": "请求标识符，无需填充"}
    },
    required=["query"]
)
async def retrieve_chunk(query: str, request_id: str = None) -> str:
    """
    检索文本块工具
    返回格式：每个片段拼接为字符串，包含file_name, file_id, file_total_pages, page_index, chunk_content
    """
    try:
        # 调用检索扩展重排方法
        results = await retriever.retrieve_expand_rerank(query)

        if not results:
            return "未找到相关的文本片段"

        # 收集 chunk 信息
        chunks_to_save = []

        # 拼接结果为统一格式
        formatted_results = []
        for result in results:
            file_url = result.get('file_url', '')
            file_id = result.get('file_id', '')
            page_index = result.get('page_index', '')
            chunk_content = result.get('chunk_content', '')
            file_total_pages = result.get('file_total_pages', '')
            chunk_index = result.get('chunk_index', '')

            # 从file_url获取原始文件名
            file_name = get_oss_original_filename(file_url) if file_url else ''

            formatted_result = (
                f"file_name:{file_name}\n"
                f"file_id:{file_id}\n"
                f"文件总页数:{file_total_pages}\n"
                f"page_index:{page_index}\n"
                f"第{page_index}页的一个文本片段(非整个页面):\n{chunk_content}\n"
            )
            formatted_results.append(formatted_result)

            # 收集 chunk 信息用于保存到redis
            if file_id is not None and chunk_index is not None:
                chunks_to_save.append({
                    "file_id": file_id,
                    "chunk_index": chunk_index
                })

        res_ = "\n\n".join(formatted_results)
        logger.info(f"查询到文本片段:\n{res_}")

        # 保存检索到的 chunk 信息
        if request_id and chunks_to_save:
            await _save_retrieval_record(
                request_id=request_id,
                tool_name="retrieve_chunk",
                records=chunks_to_save,
                tool_args={"query": query}
            )

        return res_

    except Exception as e:
        return f"检索文本块失败: {str(e)}"


@tool(
    name="get_page_content",
    description="获取指定文件下某些页面的完整内容",
    properties={
        "file_id": {"type": "integer", "description": "文件ID"},
        "page_indices": {"type": "array", "items": {"type": "integer"}, "description": "页面索引列表，代表第几页，例如 [1, 2, 3]"},
        "request_id": {"type": "string", "description": "请求唯一标识符，无需填充"}
    },
    required=["file_id", "page_indices"]
)
async def get_page_content(file_id: int, page_indices: list, request_id: str = None) -> str:
    """
    获取页面内容工具
    根据file_id和page_indices获取想要查阅的某个文件下的某些页面
    """
    try:
        result = await page_content_searcher.get_multiple_pages(file_id, page_indices)
        logger.info(f"获取到页面内容：\n{result}")

        # 保存检索记录到 Redis
        if request_id and result and not result.startswith("获取页面内容失败"):
            records = [{"file_id": file_id, "page_index": idx} for idx in page_indices]
            await _save_retrieval_record(
                request_id=request_id,
                tool_name="get_page_content",
                records=records,
                tool_args={"file_id": file_id, "page_indices": page_indices}
            )

        return result
    except Exception as e:
        return f"获取页面内容失败: {str(e)}"

