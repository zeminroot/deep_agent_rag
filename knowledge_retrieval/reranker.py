#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   reranker.py
@Author  :   zemin
@Desc    :   上下文重排：将待排序文本按照index顺序组装送入上下文重排模型
上下文重排模型使用jina-reranker-v3
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Dict, Any, Optional
from modelscope import AutoModel
from config.config import get_settings
from loguru import logger


class Reranker:
    def __init__(self, device: str = "cpu"):
        """
        初始化 Reranker 模型
        """
        self.settings = get_settings()
        self.device = device
        self.model = self.settings.rerank_model
        self._load_model()

    def _load_model(self):
        """
        加载 Reranker模型
        """
        try:
            logger.info(f"正在加载 Reranker 模型 {self.model}...")
            self.model = AutoModel.from_pretrained(
                pretrained_model_name_or_path=self.model,
                dtype="auto",
                trust_remote_code=True,
                device_map=self.device
            )
            self.model.eval()
            logger.info("Reranker 模型加载成功")
        except Exception as e:
            logger.error(f"Reranker 模型加载失败: {e}")
            raise

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        return_embeddings: bool = False
    ) -> List[Dict[str, Any]]:
        """
        对文档列表进行语义重排序

        Args:
            query: 查询文本
            documents: 待排序文档列表
            top_n: 返回前N个结果
            return_embeddings: 是否返回文档嵌入向量

        Returns:
            重排序后的结果列表，每个元素包含：
            - document: 文档内容
            - relevance_score: 相关性分数
            - index: 原始索引位置
            - embedding: 文档嵌入（return_embeddings=True时）
        """
        if not documents:
            return []

        try:
            results = self.model.rerank(
                query=query,
                documents=documents,
                top_n=top_n,
                return_embeddings=return_embeddings
            )
            return results
        except Exception as e:
            logger.error(f"文档重排序失败: {e}")
            raise

    def rerank_with_metadata(
        self,
        query: str,
        documents_with_metadata: List[Dict[str, Any]],
        top_n: Optional[int] = None,
        return_embeddings: bool = False
    ) -> List[Dict[str, Any]]:
        """
        对带元数据的文档进行重排序

        Args:
            query: 查询文本
            documents_with_metadata: 文档列表
            top_n: 返回前n个结果
            return_embeddings: 是否返回文档嵌入向量

        Returns:
            重排序后的结果列表，保留原始元数据
        """
        documents = [doc.get('chunk_content', '') for doc in documents_with_metadata]

        reranked_results = self.rerank(query, documents, top_n, return_embeddings)

        # 合并元数据
        results = []
        for rerank_item in reranked_results:
            original_index = rerank_item['index']
            original_metadata = documents_with_metadata[original_index].copy()

            result = {
                **original_metadata,
                'relevance_score': rerank_item['relevance_score'],
                'original_index': original_index
            }

            if return_embeddings and 'embedding' in rerank_item:
                result['embedding'] = rerank_item['embedding']

            results.append(result)

        return results




if __name__ == "__main__":
    import asyncio

    async def test_reranker():
        reranker = Reranker(device="cpu")

        query = "机器学习和深度学习都属于人工智能"
        documents = [
            "机器学习是什么",
            "深度学习是什么",
            "强化学习是什么",
            "机器学习与人工智能关系",
        ]

        results = reranker.rerank(query, documents)

        for result in results:
            print(result)
            print(f"Score: {result['relevance_score']:.4f}")
            print(f"Document: {result['document'][:100]}...")
            print()

    asyncio.run(test_reranker())