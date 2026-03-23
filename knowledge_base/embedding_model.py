#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   embedding_model.py
@Author  :   zemin
@Desc    :   embedding model bge
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import List, Union
from FlagEmbedding import BGEM3FlagModel
from modelscope import snapshot_download
from config.config import get_settings
import numpy as np
from loguru import logger


class EmbeddingModel:
    def __init__(
        self,
        device: str = "cpu",
    ):
        self.settings = get_settings()
        self.model_name = self.settings.embedding_model
        self.device = device or self.settings.embedding_device
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
        self.model = None
        self._load_model()

    def _download_model(self) -> str:
        """
        使用 ModelScope 下载模型到本地
        返回本地模型下载路径
        """
        try:
            logger.info(f"使用 ModelScope 下载模型: {self.model_name}")
            logger.info(f"模型缓存目录: {self.cache_dir}")
            local_path = snapshot_download(
                self.model_name,
                cache_dir=self.cache_dir,
                revision='master'
            )

            logger.success(f"模型下载成功，本地路径: {local_path}")
            return local_path

        except Exception as e:
            logger.error(f"模型下载失败: {e}")
            raise

    def _load_model(self):
        """
        加载模型，首次加载时下载模型
        """
        try:
            self.local_model_path = self._download_model()
            self.model = BGEM3FlagModel(
                self.local_model_path,
                use_fp16=True
            )
            logger.success("向量化模型加载成功")
        except Exception as e:
            logger.error(f"向量化模型加载失败: {e}")
            raise

    def encode(
        self,
        text: Union[str, List[str]],
        max_length: int = 1000
    ) -> List[List[float]]:
        try:
            if isinstance(text, str):
                text = [text]

            result = self.model.encode(
                text,
                batch_size=2,
                max_length=max_length
            )

            embeddings = result['dense_vecs']
            if hasattr(embeddings, 'tolist'):
                embeddings = embeddings.tolist()

            logger.debug(f"成功编码 {len(embeddings)} 个文本")

            return embeddings

        except Exception as e:
            logger.error(f"文本向量化失败: {e}")
            raise


    def compute_similarity(self, embeddings_1: List[List[float]], embeddings_2: List[List[float]]) -> List[List[float]]:
        """
        计算两组嵌入向量之间的相似度
        """
        # 转换为 numpy 数组
        emb1 = np.array(embeddings_1)
        emb2 = np.array(embeddings_2)
        # 计算点积（余弦相似度）
        similarity = emb1 @ emb2.T

        return similarity.tolist()


if __name__ == "__main__":
    model = EmbeddingModel()
    texts = [
        "Python编程语言",
        "人工智能计算机",
        "机器学习"
    ]
    vectors = model.encode(texts)
    print(f"编码了 {len(vectors)} 个文本")
    for i, (t, v) in enumerate(zip(texts, vectors)):
        print(t)
        print(len(v))

    embeddings_1 = model.encode(texts[0])
    embeddings_2 = model.encode(texts[1])
    similarity = model.compute_similarity(embeddings_1, embeddings_2)
    print(f"相似度矩阵: {similarity}")