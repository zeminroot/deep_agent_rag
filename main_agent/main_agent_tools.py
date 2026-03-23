#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   main_agent_tools.py
@Author  :   zemin
@Desc    :   主智能体的工具模块
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.tool_manager import tool
from knowledge_retrieval.deep_agent_rag import DeepAgentRag
from knowledge_retrieval.context_expand_twice_rerank import get_context_expand_rerank
from datetime import datetime
from loguru import logger
from utils.redis_client import save_retrieval_record
from utils.url_utils import get_oss_original_filename
from config.config import get_settings
from collections import defaultdict




# 实例化子agent
deep_agent_rag = DeepAgentRag()
logger.success("DeepAgentRag子agent初始化完成")

# 实例化上下文扩展检索器
context_expand_reranker = get_context_expand_rerank()
logger.success("ContextExpandRerank检索器初始化完成")

settings = get_settings()


@tool(
    name="knowledge_retrieval_tool",
    description="知识检索工具。专门用于从内部私有知识库中检索相关信息。适合回答需要查阅文档的事实性问题、需要具体数据支持的问题。接受经过改写/指代消解/省略恢复后的查询",
    properties={
        "queries": {"type": "array", "items": {"type": "string"}, "description": "包含经过改写/指代消解/省略恢复后的查询"},
        "request_id": {"type": "string", "description": "请求唯一标识符，无需填充"}
    },
    required=["queries"]
)
async def knowledge_retrieval_tool(queries: list, request_id: str = None) -> str:
    """
    调用检索功能，从知识库中检索相关信息
    """
    
    if settings.use_deep_agent_search == 1:
        try:
            result = await deep_agent_rag.run_batch(queries, request_id=request_id)
            # 将结果拼接返回
            return "\n\n".join(result) if result else "查询失败，无返回结果"
        except Exception as e:
            logger.error(f"DeepSearchAgent 查询失败: {e}")
            return f"查询失败: {str(e)}"
    else:
        result = await context_expand_search(queries=queries, request_id=request_id)
        return result
        

async def context_expand_search(queries: list, request_id: str = None) -> str:
    """
    上下文扩展+二次上下文重排
    执行流程：
    1. 第一次检索+重排序召回 top20 文本 chunk
    2. 根据重排序后的相似度得分进行上下文扩展（分数排名越靠前扩展越多，最多上下各10个，最少上下各1个）
    3. 对扩展后的上下文进行二次重排序，获取 top10
    4. 保存所有扩展包含的原始 chunk_index 到 Redis

    返回格式：按file_id和chunk_index排序后，格式为"文件名：xxx\n文本块内容：xxx\n\n文件名：xxx\n文本块内容：xxx"
    """
    try:
        all_query_results = []

        for query in queries:
            # 调用上下文扩展检索
            results = await context_expand_reranker.retrieve_with_context_expand(query, request_id=request_id)

            if not results:
                all_query_results.append("未找到相关的文本片段")
                continue

            # 收集所有扩展包含的原始 chunk_index 信息
            chunks_to_save = []

            # 提取需要的字段并按 file_id 和 chunk_index 排序
            simplified_results = []
            for result in results:
                file_url = result.get('file_url', '')
                file_id = result.get('file_id', '')
                chunk_content = result.get('chunk_content', '')
                chunk_index = result.get('chunk_index', '')
                original_indices = result.get('original_chunk_indices', [])

                # 从file_url获取原始文件名
                file_name = get_oss_original_filename(file_url) if file_url else ""

                simplified_results.append({
                    "file_name": file_name,
                    "file_id": file_id,
                    "chunk_index": chunk_index,
                    "chunk_content": chunk_content,
                    "original_indices": original_indices
                })

                # 收集所有扩展包含的原始 chunk_index 信息用于保存到redis
                if file_id is not None and original_indices:
                    for idx in original_indices:
                        chunks_to_save.append({
                            "file_id": file_id,
                            "chunk_index": idx
                        })

            # 按 file_id 分组聚合
            file_groups = defaultdict(list)
            for item in simplified_results:
                file_groups[item["file_id"]].append(item)

            # 对每个 file_id 下的文本块按 chunk_index 排序
            for file_id in file_groups:
                file_groups[file_id].sort(key=lambda x: x["chunk_index"])

            # 格式化输出：每个 file_id 一个条目
            formatted_parts = []
            for file_id, items in file_groups.items():
                file_name = items[0]["file_name"] if items else ""

                # 构建该文件下的所有文本块条目
                chunk_entries = []
                for item in items:
                    entry = f"---文本块{item['original_indices']}\n{item['chunk_content']}"
                    chunk_entries.append(entry)

                chunks_str = "\n".join(chunk_entries)
                formatted_part = f"文件名:{file_name}\n文本块内容:\n{chunks_str}"
                formatted_parts.append(formatted_part)

            query_result = "\n\n\n".join(formatted_parts)
            all_query_results.append(query_result)

            logger.info(f"上下文扩展检索查询到 {len(results)} 个文本片段")

            # 保存检索到的所有 chunk 信息到 Redis
            if request_id and chunks_to_save:
                # 去重：基于 file_id 和 chunk_index
                seen = set()
                unique_chunks = []
                for chunk in chunks_to_save:
                    key = (chunk["file_id"], chunk["chunk_index"])
                    if key not in seen:
                        seen.add(key)
                        unique_chunks.append(chunk)

                await save_retrieval_record(
                    request_id=request_id,
                    tool_name="context_expand_search",
                    records=unique_chunks,
                    tool_args={"query": query}
                )

        return "\n\n".join(all_query_results)
    except Exception as e:
        logger.error(f"上下文扩展检索失败: {e}")
        return f"上下文扩展检索失败: {str(e)}"