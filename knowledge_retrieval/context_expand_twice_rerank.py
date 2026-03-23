#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   context_expand_twice_rerank.py
@Author  :   zemin
@Desc    :   基于第一次检索+重排序结果，根据相似度得分进行动态上下文扩展，
             然后对扩展后的上下文进行二次重排序
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import List, Dict, Any, Optional
from loguru import logger
from knowledge_retrieval.retrieval_rerank import get_retrieval_rerank
from knowledge_retrieval.reranker import Reranker
from knowledge_base.database_sync import TextChunkRepositorySync as TextChunkRepository
from config.config import get_settings


class ContextExpandRerank:
    """
    上下文扩展+二次上下文重排序
    1. 第一次检索+上下文重排序召回 top20 文本 chunk
    2. 根据重排序后的相似度得分进行上下文扩展（分数越高扩展越多，最多上下各10个，最少上下各1个）
    3. 对扩展后的上下文进行二次重排序，获取 top10
    """

    def __init__(
        self,
        first_retrieval_top_k: int = 20,
        second_rerank_top_n: int = 10,
        max_expand_up: int = 10,
        max_expand_down: int = 10,
        min_expand: int = 1,
        overlap_threshold: int = 50
    ):
        """
        初始化 ContextExpandRerank

        Args:
            first_retrieval_top_k: 第一次检索返回的文档数量
            second_rerank_top_n: 二次重排序后返回的文档数量
            max_expand_up: 向上扩展的最大chunk数
            max_expand_down: 向下扩展的最大chunk数
            min_expand: 最小扩展数量，默认1
            overlap_threshold: 文本去重阈值，默认50个字符
        """
        self.retrieval_rerank = get_retrieval_rerank()
        self.reranker = None
        self.first_retrieval_top_k = first_retrieval_top_k
        self.second_rerank_top_n = second_rerank_top_n
        self.max_expand_up = max_expand_up
        self.max_expand_down = max_expand_down
        self.min_expand = min_expand
        self.overlap_threshold = overlap_threshold
        self._init_components()

    def _init_components(self):
        """
        初始化组件
        """
        settings = get_settings()
        self.reranker = Reranker(device=settings.rerank_device)

    def _calculate_expand_count(self, rank: int, total_count: int) -> tuple:
        """
        根据排名计算上下文扩展数量
        排名越靠前（数值越小），扩展越多

        Args:
            rank: 排名，从0开始（0表示第1名，1表示第2名，以此类推）
            total_count: 总结果数量

        Returns:
            (up_count, down_count): 向上和向下扩展的数量
        """
        if total_count <= 1:
            return self.max_expand_up, self.max_expand_down

        # 将排名归一化到 [0, 1] 范围，0表示第1名，1表示最后一名
        ratio = rank / (total_count - 1)

        # 计算扩展数量：排名第1,2扩展最多(10个)，排名最后扩展最少(1个)
        expand_range = self.max_expand_up - self.min_expand
        expand_count = int(self.max_expand_up - ratio * expand_range)
        expand_count = max(self.min_expand, min(self.max_expand_up, expand_count))

        # 上下各扩展相同数量
        return expand_count, expand_count

    async def _get_context_chunks(
        self,
        file_id: int,
        chunk_index: int,
        expand_up: int,
        expand_down: int
    ) -> List[Dict[str, Any]]:
        """
        获取指定文本块周围的上下文文本块

        Args:
            file_id: 文件ID
            chunk_index: 文本块索引
            expand_up: 向上扩展的数量
            expand_down: 向下扩展的数量

        Returns:
            上下文文本块列表
        """
        try:
            indices = []

            # 向上的chunk
            for i in range(1, expand_up + 1):
                idx = chunk_index - i
                if idx >= 0:
                    indices.append(idx)

            # 当前的chunk
            indices.append(chunk_index)

            # 向下的chunk
            for i in range(1, expand_down + 1):
                idx = chunk_index + i
                indices.append(idx)

            # 批量查询文本块
            context_chunks_db = TextChunkRepository.get_chunks_by_file_id_and_indices(
                file_id=file_id,
                chunk_indices=indices
            )

            context_chunks = []
            for chunk in context_chunks_db:
                context_chunks.append({
                    'chunk_content': chunk.chunk_content,
                    'chunk_index': chunk.chunk_index,
                    'page_id': chunk.page_id,
                    'file_id': chunk.file_id
                })

            return context_chunks

        except Exception as e:
            logger.error(f"获取上下文文本块失败: {e}")
            return []

    def _merge_chunks_with_deduplication(
        self,
        chunks: List[Dict[str, Any]]
    ) -> str:
        """
        合并多个文本块，去重重叠内容。chunks: 文本块列表
        返回合并后的文本
        """
        if not chunks:
            return ""

        if len(chunks) == 1:
            return chunks[0]['chunk_content']

        # 按 chunk_index 升序排序
        sorted_chunks = sorted(chunks, key=lambda x: x['chunk_index'])
        merged = sorted_chunks[0]['chunk_content']

        for i in range(1, len(sorted_chunks)):
            current_chunk = sorted_chunks[i]['chunk_content']
            merged = self._concat_with_overlap_removal(merged, current_chunk)

        return merged

    def _concat_with_overlap_removal(
        self,
        text1: str,
        text2: str
    ) -> str:
        """
        拼接两段文本，去除重叠部分
        """
        if not text1:
            return text2

        if not text2:
            return text1

        # 查找最大重叠
        max_overlap = min(len(text1), len(text2))
        overlap_len = 0

        # 从最大可能的长度开始查找
        for i in range(max_overlap, 0, -1):
            if text1[-i:] == text2[:i]:
                overlap_len = i
                break

        # 只有重叠长度大于阈值才进行去重
        if overlap_len >= self.overlap_threshold:
            return text1 + text2[overlap_len:]
        else:
            return text1 + "\n" + text2

    async def retrieve_with_context_expand(
        self,
        query: str,
        request_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        执行上下文扩展二次重排序检索

        流程：
        1. 第一次检索+重排序召回 top20 文本 chunk
        2. 根据重排序后的相似度得分计算上下文扩展数量（分数越高扩展越多）
        3. 对每个文本块进行上下文扩展
        4. 对扩展后的上下文进行二次重排序，获取 top10

        Args:
            query: 查询文本
            request_id: 请求ID，用于保存检索记录

        Returns:
            二次重排序后的文档列表，每项包含：
            - chunk_content: 扩展后的文档内容
            - chunk_index: 中心文本块索引
            - page_id: 页面ID
            - page_index: 页面索引
            - file_id: 文件ID
            - file_url: 文件URL
            - file_total_pages: 文件总页数
            - relevance_score: 二次重排序后的相关性分数
            - original_chunk_indices: 扩展包含的所有原始chunk索引列表
        """
        try:
            logger.info(f"开始上下文扩展二次重排序检索，query: {query}")

            # 1、第一次检索+重排序，召回 top20
            logger.info(f"第一次检索+重排序，召回 top{self.first_retrieval_top_k}")
            first_results = self.retrieval_rerank.retrieve(query, top_n=self.first_retrieval_top_k)

            if not first_results:
                logger.warning("第一次检索无结果")
                return []

            logger.info(f"第一次检索返回 {len(first_results)} 个结果")

            # 2、根据排名进行上下文扩展
            expanded_documents = []
            total_results = len(first_results)
            for rank, result in enumerate(first_results):
                file_id = result.get('file_id')
                chunk_index = result.get('chunk_index')
                score = result.get('relevance_score', 0.5)

                if file_id is None or chunk_index is None:
                    # 没有足够信息，直接使用原结果
                    expanded_doc = {
                        **result,
                        'original_chunk_indices': [chunk_index] if chunk_index is not None else []
                    }
                    expanded_documents.append(expanded_doc)
                    continue

                # 根据排名计算扩展数量（排名rank=0,即第1名扩展最多）
                expand_up, expand_down = self._calculate_expand_count(rank, total_results)

                logger.debug(
                    f"文本块 {chunk_index} 得分 {score:.4f}, "
                    f"向上扩展 {expand_up} 个，向下扩展 {expand_down} 个"
                )

                # 获取上下文文本块
                context_chunks = await self._get_context_chunks(
                    file_id=file_id,
                    chunk_index=chunk_index,
                    expand_up=expand_up,
                    expand_down=expand_down
                )

                if not context_chunks:
                    # 无法获取上下文，使用原结果
                    expanded_doc = {
                        **result,
                        'original_chunk_indices': [chunk_index]
                    }
                    expanded_documents.append(expanded_doc)
                    continue

                # 合并上下文文本块
                expanded_content = self._merge_chunks_with_deduplication(context_chunks)

                # 收集所有包含的原始chunk索引
                original_indices = [c['chunk_index'] for c in context_chunks]

                # 构建扩展后的文档
                expanded_doc = {
                    **result,
                    'chunk_content': expanded_content,
                    'original_chunk_indices': sorted(original_indices),
                    'expand_up': expand_up,
                    'expand_down': expand_down,
                    'first_score': score
                }
                expanded_documents.append(expanded_doc)

            logger.info(f"上下文扩展完成，共 {len(expanded_documents)} 个扩展文档")

            # 3、对扩展后的文档进行二次重排序
            logger.info(f"开始二次上下文重排序，返回 top{self.second_rerank_top_n}")

            # 准备重排序数据
            documents_for_rerank = []
            for doc in expanded_documents:
                documents_for_rerank.append({
                    'chunk_content': doc['chunk_content'],
                    'chunk_index': doc['chunk_index'],
                    'page_id': doc.get('page_id'),
                    'page_index': doc.get('page_index'),
                    'file_id': doc.get('file_id'),
                    'file_url': doc.get('file_url'),
                    'file_total_pages': doc.get('file_total_pages'),
                    'original_chunk_indices': doc.get('original_chunk_indices', []),
                    'expand_up': doc.get('expand_up', 0),
                    'expand_down': doc.get('expand_down', 0),
                    'first_score': doc.get('first_score', 0)
                })

            # 执行二次重排序
            second_reranked_results = self.reranker.rerank_with_metadata(
                query=query,
                documents_with_metadata=documents_for_rerank,
                top_n=self.second_rerank_top_n
            )

            logger.info(f"二次重排序完成，返回 {len(second_reranked_results)} 个结果")

            return second_reranked_results

        except Exception as e:
            logger.error(f"上下文扩展二次重排序检索失败: {e}")
            raise


# 全局实例缓存
_context_expand_rerank: Optional[ContextExpandRerank] = None

def get_context_expand_rerank() -> ContextExpandRerank:
    """
    获取 ContextExpandRerank 单例实例
    """
    global _context_expand_rerank
    if _context_expand_rerank is None:
        _context_expand_rerank = ContextExpandRerank()
    return _context_expand_rerank


if __name__ == "__main__":
    import asyncio

    async def test_context_expand_rerank():
        retriever = get_context_expand_rerank()

        query = "安全风险都指哪些"
        results = await retriever.retrieve_with_context_expand(query)

        print(f"上下文扩展二次重排序结果（共{len(results)}条）")
        
    asyncio.run(test_context_expand_rerank())
