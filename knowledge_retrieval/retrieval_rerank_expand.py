#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   retrieval_rerank_expand.py
@Author  :   zemin
@Desc    :   基于一次重排序结果，对文本chunk分别向上下扩展文本块
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import List, Dict, Any, Optional
from loguru import logger
from knowledge_retrieval.retrieval_rerank import get_retrieval_rerank
from knowledge_base.database_sync import TextChunkRepositorySync as TextChunkRepository
from config.config import get_settings
from knowledge_base.es_vector_store import ESVectorStore
from knowledge_retrieval.reranker import Reranker



class RetrievalRerankExpand:
    def __init__(
        self,
        overlap_threshold: int = 50,
        vector_top_k: int = 20,
        rerank_top_n: int = 10
    ):
        """
        overlap_threshold: 文本去重阈值
        vector_top_k: 向量检索返回的文档数量
        rerank_top_n: 重排序后返回的文档数量
        """
        self.retrieval_rerank = get_retrieval_rerank()
        self.overlap_threshold = overlap_threshold
        self.vector_top_k = vector_top_k
        self.rerank_top_n = rerank_top_n
        self._init_components()

    def _init_components(self):
        """
        初始化加载重排和检索器
        """
        settings = get_settings()
        self.es_vector_store = ESVectorStore(
            hosts=f"http://{settings.es_host}:{settings.es_port}",
            index_name=settings.es_index_knowledge,
            vector_dim=1024,
            similarity="cosine",
            es_user=settings.es_user,
            es_password=settings.es_password
        )
        self.reranker = Reranker(device=settings.rerank_device)


    async def retrieve_expand_rerank(
        self,
        query: str,
        vector_top_k: Optional[int] = None,
        rerank_top_n: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        先向量检索获取 top20，对每个文本块进行上下文扩展后再重排序取 top10
        返回扩展后重排序的文档列表，每个文档元素包含：
            - chunk_content: 扩展后的文档内容
            - chunk_index: 原始文本块在页面中的索引
            - page_id: 页面ID
            - page_index: 页面索引
            - file_id: 文件ID
            - file_url: 文件URL
            - file_total_pages: 文件总页数
            - relevance_score: 相关性分数
        """
        try:
            vector_top_k = vector_top_k or self.vector_top_k
            rerank_top_n = rerank_top_n or self.rerank_top_n

            # 1、向量检索获取 top_k 文本块
            logger.info(f"开始向量检索，query: {query[:50]}..., vector_top_k: {vector_top_k}")
            vector_results = self.es_vector_store.hybrid_search(
                query_text=query,
                k=vector_top_k,
                num_candidates=100,
                text_weight=0.3,
                vector_weight=0.7,
                source_fields=None
            )
            logger.info(f"向量检索返回 {len(vector_results)} 个结果")

            # 2、转换为标准格式并按文件分组排序
            file_groups = {}
            for hit in vector_results:
                source = hit.get('_source', {})
                file_id = source.get('file_id')
                if file_id is None:
                    file_id = 'none'
                if file_id not in file_groups:
                    file_groups[file_id] = []
                file_groups[file_id].append(hit)

            sorted_results = []
            for file_id in sorted(file_groups.keys()):
                chunks = file_groups[file_id]
                chunks_sorted = sorted(
                    chunks,
                    key=lambda x: x.get('_source', {}).get('chunk_index', 0)
                )
                sorted_results.extend(chunks_sorted)

            # 3、准备扩展前的文档数据
            documents_with_metadata = []
            for hit in sorted_results:
                source = hit.get('_source', {})
                documents_with_metadata.append({
                    'chunk_content': source.get('chunk_content', ''),
                    'chunk_index': source.get('chunk_index', 0),
                    'page_id': source.get('page_id'),
                    'page_index': source.get('page_index'),
                    'file_id': source.get('file_id'),
                    'file_url': source.get('file_url'),
                    'file_total_pages': source.get('file_total_pages'),
                    'id': source.get('id'),
                    '_id': hit.get('_id')
                })

            # 4、对每个文本块进行上下文扩展
            logger.info(f"开始对 {len(documents_with_metadata)} 个文本块进行上下文扩展")
            expanded_documents = []
            for doc in documents_with_metadata:
                file_id = doc.get('file_id')
                chunk_index = doc.get('chunk_index')

                if file_id is None:
                    # 没有 file_id，直接使用原结果
                    expanded_documents.append(doc)
                    continue

                # 获取同一文件下的相邻文本块
                adjacent_chunks = await self._get_adjacent_chunks(file_id, chunk_index)
                adjacent_chunks.append({
                    "chunk_content": doc["chunk_content"],
                    "chunk_index": chunk_index
                })

                # 合并扩展内容
                expanded_content = self._merge_chunks_with_deduplication(adjacent_chunks)
                doc['chunk_content'] = expanded_content
                expanded_documents.append(doc)
                logger.debug(f"文本块 {chunk_index} 已扩展。")

            logger.info(f"上下文扩展完成，共扩展 {len(expanded_documents)} 个结果")

            # 5、对扩展后的结果进行语义重排序
            logger.info(f"开始语义重排序，文档数量: {len(expanded_documents)}, 返回 top{rerank_top_n}")
            reranked_results = self.reranker.rerank_with_metadata(
                query=query,
                documents_with_metadata=expanded_documents,
                top_n=rerank_top_n
            )

            logger.info(f"重排序完成，返回 top{len(reranked_results)} 结果")

            return reranked_results

        except Exception as e:
            logger.error(f"检索扩展重排失败: {e}")
            raise


    async def _get_adjacent_chunks(
        self,
        file_id: int,
        chunk_index: int
    ) -> List[Dict[str, Any]]:
        """
        获取某个文件下指定文本块的相邻文本块。file_id: 文件ID。chunk_index: 文本块索引
        返回相邻文本块列表
            [{
                'chunk_content': chunk.chunk_content,
                'chunk_index': chunk.chunk_index
            }]
        """
        try:
            # 计算相邻的 chunk_index
            adjacent_indices = []
            if chunk_index > 0:
                adjacent_indices.append(chunk_index - 1)
            adjacent_indices.append(chunk_index + 1)

            # 批量查询相邻文本块
            adjacent_chunks_db = TextChunkRepository.get_chunks_by_file_id_and_indices(
                file_id=file_id,
                chunk_indices=adjacent_indices
            )

            # 转换为标准格式
            adjacent_chunks = []
            for chunk in adjacent_chunks_db:
                adjacent_chunks.append({
                    'chunk_content': chunk.chunk_content,
                    'chunk_index': chunk.chunk_index
                })

            return adjacent_chunks

        except Exception as e:
            logger.error(f"获取相邻文本块失败: {e}")
            return []
        
    
    def _merge_chunks_with_deduplication(
        self,
        chunks: List[Dict[str, Any]],
        order: str = "asc"
    ) -> str:
        """
        合并多个文本块，去重重叠内容

        Args:
            chunks: 文本块列表，每个chunk包含chunk_content和chunk_index
            order: 合并顺序，"asc"按chunk_index升序，"desc"按chunk_index降序

        Returns:
            合并后的文本
        """
        if not chunks:
            return ""

        if len(chunks) == 1:
            return chunks[0]['chunk_content']

        if order == "asc":
            sorted_chunks = sorted(chunks, key=lambda x: x['chunk_index'])
        else:
            sorted_chunks = sorted(chunks, key=lambda x: x['chunk_index'], reverse=True)

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
            # 去除重叠部分后拼接
            return text1 + text2[overlap_len:]
        else:
            # 重叠太小，或无重叠，直接用分隔符拼接
            return text1 + "\n" + text2



if __name__ == "__main__":
    import asyncio

    async def test_retrieval_rerank_expand():
        retriever = RetrievalRerankExpand()

        query = "安全风险都指哪些"
        # results = await retriever.retrieve_with_expand(query)
        results = await retriever.retrieve_expand_rerank(query)

        print(f"=== 检索扩展结果（共{len(results)}条）===")

    asyncio.run(test_retrieval_rerank_expand())
    
    
    
    