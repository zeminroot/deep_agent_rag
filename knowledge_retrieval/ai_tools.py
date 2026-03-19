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
from loguru import  logger


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
        from loguru import logger
        logger.warning(f"系统提示词文件未找到: {prompt_file}")
        return "你是一个专业的知识检索助手。借助工具像人类研究员一样主动翻页查找文档资料。"
    except Exception as e:
        from loguru import logger
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


# 实例化检索扩展重排服务
retriever = RetrievalRerankExpand()
# 实例化页面内容搜索服务
page_content_searcher = PageContentSearch()


@tool(
    name="retrieve_chunk",
    description="从知识库中检索相关的文本块。召回top10相关文本片段",
    properties={
        "query": {"type": "string", "description": "检索查询文本"}
    },
    required=["query"]
)
async def retrieve_chunk(query: str) -> str:
    """
    检索文本块工具
    返回格式：每个片段拼接为字符串，包含file_name, file_id, file_total_pages, page_index, chunk_content
    """
    try:
        # 调用检索扩展重排方法
        results = await retriever.retrieve_expand_rerank(query)

        if not results:
            return "未找到相关的文本片段"

        # 拼接结果为统一格式
        formatted_results = []
        for result in results:
            file_url = result.get('file_url', '')
            file_id = result.get('file_id', '')
            page_index = result.get('page_index', '')
            chunk_content = result.get('chunk_content', '')
            file_total_pages = result.get('file_total_pages', '')

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
        res_ = "\n\n".join(formatted_results)
        logger.info(f"查询到文本片段:\n{res_}")

        return res_

    except Exception as e:
        return f"检索文本块失败: {str(e)}"


@tool(
    name="get_page_content",
    description="获取指定文件下某些页面的完整内容",
    properties={
        "file_id": {"type": "integer", "description": "文件ID"},
        "page_indices": {"type": "array", "items": {"type": "integer"}, "description": "页面索引列表，例如 [1, 2, 3]"}
    },
    required=["file_id", "page_indices"]
)
async def get_page_content(file_id: int, page_indices: list) -> str:
    """
    获取页面内容工具
    根据file_id和page_indices获取想要查阅的某个文件下的某些页面
    """
    try:
        result = await page_content_searcher.get_multiple_pages(file_id, page_indices)
        logger.info(f"获取到页面内容：\n{result}")
        return result
    except Exception as e:
        return f"获取页面内容失败: {str(e)}"

