#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   config.py
@Author  :   zemin
@Desc    :   配置文件，从.env文件加载
'''


import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import List
from functools import lru_cache

ENV_FILE = os.path.join(BASE_DIR, ".env")


class Settings(BaseSettings):
    # MySQL配置
    database_url: str

    # Redis配置
    redis_host: str
    redis_port: int
    redis_db: int
    redis_password: str
    redis_state_ttl: int = 86400  # 过期时间，默认24小时

    # OSS配置
    oss_access_key_id: str
    oss_access_key_secret: str
    oss_endpoint: str
    oss_bucket_name: str
    oss_region: str

    # Elasticsearch配置
    es_host: str
    es_port: int
    es_user: str
    es_password: str
    es_index_knowledge: str = "rag_knowledge"  # 知识库索引名
    es_index_memory: str = "rag_memory"  # 记忆索引名
    es_index_dialogue: str = "rag_dialogue"  # 对话索引名 

    # 应用配置
    debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # 文件上传配置
    max_file_size_mb: int = 100
    allowed_file_types: str = "image/jpeg,image/png,application/pdf"  # 英文逗号分隔

    # LLM配置
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_temperature: float = 0.7
    llm_max_tokens: int = 10240

    # 文档解析API配置
    paddleocr_api_url: str
    paddleocr_api_token: str

    # 检索排序模型配置
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    rerank_model: str = "jinaai/jina-reranker-v3"
    rerank_device: str = "cpu"

    # 检索配置
    vector_top_k: int = 10
    bm25_top_k: int = 10
    rerank_top_n: int = 2

    # 分布式锁配置
    lock_key_prefix: str = "rag:lock:"
    lock_expire_time: int = 300  # 锁过期时间（秒）

    # 对话记忆配置
    dialogue_memory_window_size: int = 10
    memory_summary_time: str = "02:00"

    # 定时任务配置
    db_scan_interval: int = 1

    @property
    def max_upload_size(self) -> int:
        """
        最大上传大小（字节）
        """
        return self.max_file_size_mb * 1024 * 1024

    @property
    def redis_url(self) -> str:
        """
        Redis连接URL
        """
        return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def es_url(self) -> str:
        """
        Elasticsearch连接URL
        """
        return f"https://{self.es_user}:{self.es_password}@{self.es_host}:{self.es_port}"

    @property
    def allowed_file_types_list(self) -> List[str]:
        """
        将逗号分隔的字符串转换为列表
        """
        return [t.strip() for t in self.allowed_file_types.split(",")]

    model_config = ConfigDict(
        env_file=ENV_FILE,  # 配置文件.env的位置
        env_file_encoding="utf-8",
        case_sensitive=False
    )


@lru_cache()
def get_settings() -> Settings:
    """
    获取配置实例
    """
    return Settings()
