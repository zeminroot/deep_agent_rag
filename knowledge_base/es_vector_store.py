#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   es_vector_store.py
@Author  :   zemin
@Desc    :   ES向量存储与检索，集成文本向量化功能
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import List, Dict, Any, Optional, Union
from elasticsearch import Elasticsearch, helpers
from knowledge_base.embedding_model import EmbeddingModel
from loguru import logger


class ESVectorStore:
    def __init__(
        self,
        hosts: Union[str, List[str]],
        index_name: str,
        vector_field: str = "embedding",
        text_field: str = "chunk_content",
        vector_dim: int = 1024,
        similarity: str = "cosine",
        es_user: str = "",
        es_password: str = "",
        **es_kwargs
    ):
        self.index_name = index_name
        self.vector_field = vector_field
        self.text_field = text_field
        self.vector_dim = vector_dim
        self.similarity = similarity

        # 初始化 ES 客户端
        self.es = Elasticsearch(hosts, basic_auth=(es_user, es_password), verify_certs=False, **es_kwargs)
        if not self.es.ping():
            raise ConnectionError("无法连接到 Elasticsearch")

        # 初始化向量化模型
        self.embedding_model = EmbeddingModel()


    def create_index(self, shards: int = 1, replicas: int = 1, overwrite: bool = True) -> bool:
        """
        创建索引，定义 mappings
        """
        if self.es.indices.exists(index=self.index_name):
            if overwrite:
                self.es.indices.delete(index=self.index_name)
                logger.info(f"已删除索引: {self.index_name}")
            else:
                logger.info(f"索引 {self.index_name} 已存在，跳过创建")
                return False

        mappings = {
            "properties": {
                self.vector_field: {
                    "type": "dense_vector",
                    "dims": self.vector_dim,
                    "index": True,
                    "similarity": self.similarity,
                },
                "id": {"type": "integer"},
                "chunk_content": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "chunk_index": {"type": "integer"},
                "page_id": {"type": "integer"},
                "page_index": {"type": "integer"},
                "file_id": {"type": "integer"},
                "file_url": {"type": "keyword"},
                "file_total_pages": {"type": "integer"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"}
            }
        }
        settings = {"number_of_shards": shards, "number_of_replicas": replicas}

        try:
            self.es.indices.create(index=self.index_name, mappings=mappings, settings=settings)
            logger.info(f"索引 {self.index_name} 创建成功")
            return True
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            raise


    def bulk_index(self, documents: List[Dict[str, Any]], chunk_size: int = 100) -> tuple:
        """
        批量索引文档
        documents: 文档列表，每个元素包含chunk的全部信息
        chunk_size: 每批处理的文档数
        返回(success_count, error_count)
        """
        actions = []
        for doc in documents:
            if len(doc[self.vector_field]) != self.vector_dim:
                raise ValueError(f"文档 {doc.get('_id')} 向量维度不匹配")

            # 构建_source，只保留需要的字段
            source = {self.vector_field: doc[self.vector_field]}
            if "id" in doc:
                source["id"] = doc["id"]
            if "chunk_content" in doc:
                source["chunk_content"] = doc["chunk_content"]
            if "chunk_index" in doc:
                source["chunk_index"] = doc["chunk_index"]
            if "page_id" in doc:
                source["page_id"] = doc["page_id"]
            if "page_index" in doc:
                source["page_index"] = doc["page_index"]
            if "file_id" in doc:
                source["file_id"] = doc["file_id"]
            if "file_url" in doc:
                source["file_url"] = doc["file_url"]
            if "file_total_pages" in doc:
                source["file_total_pages"] = doc["file_total_pages"]
            if "created_at" in doc:
                source["created_at"] = doc["created_at"]
            if "updated_at" in doc:
                source["updated_at"] = doc["updated_at"]

            actions.append({
                "_index": self.index_name,
                "_id": doc["_id"],
                "_source": source,
            })

        try:
            success, errors = helpers.bulk(
                self.es, actions, chunk_size=chunk_size, stats_only=False, raise_on_error=False, refresh=True
            )
            failed = len(errors) if errors else 0
            logger.info(f"批量构建完成: {success} 成功, {failed} 失败")

            # 记录详细的错误信息
            if errors:
                for i, error in enumerate(errors[:5]):  # 只显示前5个错误避免日志过多
                    logger.error(f"ES写入错误 {i+1}: {error}")

            return success, failed
        except Exception as e:
            logger.error(f"批量索引过程中发生异常: {e}")
            raise


    def search_vector(
        self,
        query_vector: Optional[List[float]] = None,
        query_text: Optional[str] = None,
        k: int = 20,
        num_candidates: int = 100,
        source_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        向量相似性检索KNN
        query_vector: 查询向量，不传自动对query_text向量化
        query_text: 查询文本，不传使用query_vector
        k: 返回的最相似文档数量
        num_candidates: 每个分片考虑的候选文档数
        source_fields: 需要返回的字段列表
        返回文档列表，每项包含 "_id", "_score", "_source"
        """
        if query_vector is None and query_text is not None:
            query_vector = self.embedding_model.encode(query_text)[0]

        if len(query_vector) != self.vector_dim:
            raise ValueError(f"查询向量维度必须为 {self.vector_dim}")

        query = {
            "knn": {
                "field": self.vector_field,
                "query_vector": query_vector,
                "k": k,
                "num_candidates": num_candidates,
            }
        }
        if source_fields:
            query["_source"] = source_fields

        response = self.es.search(index=self.index_name, body=query)
        return [hit for hit in response["hits"]["hits"]]


    def search_text_fuzzy(
        self,
        query_text: str,
        size: int = 20,
        fuzziness: str = "AUTO",
        source_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        文本模糊检索（使用 BM25 进行整段文本相似度匹配）
        """
        query = {
            "query": {
                "match": {self.text_field: query_text}
            },
            "size": size,
        }
        if source_fields:
            query["_source"] = source_fields

        response = self.es.search(index=self.index_name, body=query)
        return [hit for hit in response["hits"]["hits"]]


    def hybrid_search(
        self,
        query_text: Optional[str] = None,
        k: int = 10,
        num_candidates: int = 100,
        text_weight: float = 0.5,
        vector_weight: float = 0.5,
        source_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        混合检索：结合向量相似度和文本模糊检索。
        query_text: 查询文本
        k: 返回文档数量
        num_candidates: 向量检索的候选数
        text_weight: 文本匹配得分权重
        vector_weight: 向量相似度得分权重
        source_fields: 需要返回的字段列表
        返回文档列表
        """
        query_vector = self.embedding_model.encode(query_text)[0]

        if len(query_vector) != self.vector_dim:
            raise ValueError(f"查询向量维度必须为 {self.vector_dim}")

        script = {
            "source": f"(cosineSimilarity(params.query_vector, '{self.vector_field}') + 1.0) * params.vector_weight + _score * params.text_weight",
            "params": {"query_vector": query_vector, "vector_weight": vector_weight, "text_weight": text_weight},
        }

        query = {
            "size": k,
            "query": {
                "script_score": {
                    "query": {"match": {self.text_field: query_text}},
                    "script": script,
                }
            },
        }
        if source_fields:
            query["_source"] = source_fields

        response = self.es.search(index=self.index_name, body=query)
        return [hit for hit in response["hits"]["hits"]]


    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 ID 获取文档
        """
        try:
            response = self.es.get(index=self.index_name, id=doc_id)
            return response["_source"]
        except Exception:
            return None

    def delete_document(self, doc_id: str, refresh: bool = True) -> bool:
        """
        删除文档
        """
        try:
            self.es.delete(index=self.index_name, id=doc_id, refresh=refresh)
            logger.debug(f"文档 {doc_id} 已删除")
            return True
        except Exception as e:
            logger.error(f"删除文档 {doc_id} 失败: {e}")
            return False


if __name__ == "__main__":
    import os
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config.config import get_settings

    cfg = get_settings()

    store = ESVectorStore(
        hosts=f"http://{cfg.es_host}:{cfg.es_port}",
        index_name=cfg.es_index_knowledge,
        vector_dim=1024,
        similarity="cosine",
        es_user=cfg.es_user,
        es_password=cfg.es_password
    )

    # # 创建索引
    # store.create_index(overwrite=True)

    # results = store.search_vector(query_text="安全风险", k=2)
    # logger.info(f"文本向量检索结果:\n{results}")
    # for hit in results:
    #     logger.info(f"ID: {hit['_id']}, Score: {hit['_score']:.4f}, Content: {hit['_source'].get('chunk_content', '')}")

    # text_results = store.search_text_fuzzy("安全风险", fuzziness="AUTO", size=2)
    # logger.info("模糊检索结果:")
    # for hit in text_results:
    #     logger.info(f"ID: {hit['_id']}, Score: {hit['_score']:.4f}, Content: {hit['_source'].get('chunk_content', '')}")

    # hybrid_results = store.hybrid_search(
    #     query_text="安全风险",
    #     k=2,
    #     text_weight=0.3,
    #     vector_weight=0.7,
    # )
    # logger.info("混合检索结果:")
    # for hit in hybrid_results:
    #     logger.info(f"ID: {hit['_id']}, Score: {hit['_score']:.4f}, Content: {hit['_source'].get('chunk_content', '')}")
