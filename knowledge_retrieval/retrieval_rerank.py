#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   retrieval_rerank.py
@Author  :   zemin
@Desc    :   向量检索+上下文重排
'''
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import List, Dict, Any, Optional
from loguru import logger
from functools import lru_cache
from config.config import get_settings
from knowledge_base.es_vector_store import ESVectorStore
from knowledge_retrieval.reranker import Reranker


class RetrievalRerank:
    def __init__(
        self,
        vector_top_k: int = 20,
        rerank_top_n: int = 10
    ):
        """
        初始化 RetrievalRerank

        Args:
            vector_top_k: 向量检索返回的文档数量，默认为20
            rerank_top_n: 重排序后返回的文档数量，默认为10
        """
        self.es_vector_store = None
        self.reranker = None
        self.vector_top_k = vector_top_k
        self.rerank_top_n = rerank_top_n
        self._init_components()

    def _init_components(self):
        """
        初始化组件
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


    def retrieve(
        self,
        query: str,
        top_n: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        检索并重排序文档。query: 查询文本。top_n: 返回的文档数量
        返回重排序后的文档列表，每项包含：chunk在es中的全部信息+relevance_score: 相关性分数
        """

        top_n = top_n or self.rerank_top_n

        try:
            # 1、使用混合检索（向量 + 文本）获取top20文本块
            logger.info(f"开始向量检索，query: {query[:15]}...")
            vector_results = self.es_vector_store.hybrid_search(
                query_text=query,
                k=20,
                num_candidates=100,
                text_weight=0.3,
                vector_weight=0.7,
                source_fields=None
            )
            logger.info(f"向量检索返回结果：{vector_results}")


            # 2、以 file_id 为单位，按 chunk_index 从小到大排序
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

            logger.info(f"以文件id为单位，按照chunk_index排序后的结果{sorted_results}")

            # 3、准备重排序数据
            documents_with_metadata = []
            for hit in sorted_results:
                source = hit.get('_source', {})
                documents_with_metadata.append({
                    'chunk_content': source.get('chunk_content', ''),
                    'chunk_index': source.get('chunk_index', 0),
                    'page_id': source.get('page_id'),
                    'page_index': source.get('page_index'), 
                    'file_id': source.get('file_id'),
                    'file_url':source.get('file_url'),
                    'file_total_pages':source.get('file_total_pages'),
                    'id': source.get('id'),
                    '_id': hit.get('_id')
                })

            # 4、语义重排序
            logger.info(f"开始语义重排序，文档数量: {len(documents_with_metadata)}")
            reranked_results = self.reranker.rerank_with_metadata(
                query=query,
                documents_with_metadata=documents_with_metadata,
                top_n=top_n
            )

            logger.info(f"重排序完成，返回 top{len(reranked_results)} 结果")

            return reranked_results

        except Exception as e:
            logger.error(f"检索失败: {e}")
            raise



@lru_cache()
def get_retrieval_rerank() -> RetrievalRerank:
    """
    获取 RetrievalRerank 实例
    """
    _retrieval_rerank = RetrievalRerank()
    return _retrieval_rerank


if __name__ == "__main__":
    import asyncio

    async def test_retrieval_rerank():
        retriever = get_retrieval_rerank()

        query = "我饭店里使用的天然气算是风险点吗"
        results = retriever.retrieve(query)

        print(f"检索结果\n")
        for i, result in enumerate(results, 1):
            print(f"\n[{i}] 相关度: {result['relevance_score']:.4f}")
            print(f"内容: {result['chunk_content'][:150]}...")
            print(f"文件ID: {result['file_id']}, 页面ID: {result['page_id']}, 文本块索引: {result['chunk_index']}")

    asyncio.run(test_retrieval_rerank())