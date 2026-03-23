#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   oss_service.py
@Author  :   zemin
@Desc    :   阿里云OSS文件操作
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from typing import Optional
from functools import lru_cache
from loguru import logger
from oss2 import Auth, Bucket
from config.config import get_settings


class OSSService:
    """
    OSS 文件上传服务类
    """

    def __init__(self):
        """
        初始化 OSS 服务
        """
        settings = get_settings()
        self.auth = Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        self.bucket = Bucket(
            self.auth,
            settings.oss_endpoint,
            settings.oss_bucket_name,
            region=settings.oss_region
        )
        self.bucket_name = settings.oss_bucket_name
        self.endpoint = settings.oss_endpoint


    def _generate_object_name(self, filename: str, prefix: str = "uploads") -> str:
        """
        生成OSS对象名

        Args:
            filename: 原始文件名
            prefix: 路径前缀

        Returns:
            OSS对象名
        """
        split_res = os.path.splitext(filename)
        fname = split_res[0]
        # 文件扩展名
        ext = split_res[1]
        # 生成唯一文件名
        unique_name = f"{uuid.uuid4().hex}-{fname}{ext}"
        return f"{prefix}/{unique_name}"


    def upload_file(
        self,
        file_path: str,
        filename: Optional[str] = None,
        prefix: str = "uploads"
    ) -> str:
        """
        上传本地文件到 OSS

        Args:
            file_path: 本地文件路径
            filename: 不传原文件名生成唯一文件名
            prefix: OSS路径前缀

        Returns:
            OSS文件URL
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 使用原始文件名或生成唯一文件名
        if filename:
            object_name = self._generate_object_name(filename, prefix)
        else:
            object_name = self._generate_object_name(os.path.basename(file_path), prefix)

        # 上传文件
        try:
            self.bucket.put_object_from_file(object_name, file_path)
            # self.bucket.put_object_acl(object_name, 'public-read')
            logger.info(f"文件上传成功: {object_name}")

            return self._get_file_url(object_name)
        except Exception as e:
            logger.error(f"文件上传失败: {e}")
            raise


    def _get_file_url(self, object_name: str, expires: int = 3600) -> str:
        """
        获取文件访问 URL

        Args:
            object_name: OSS对象名
            expires: URL 过期时间（秒），默认 1 小时

        Returns:
            文件访问 URL
        """
        return f"https://{self.bucket_name}.{self.endpoint}/{object_name}"



@lru_cache(maxsize=None)
def get_oss_service() -> OSSService:
    """
    获取 OSS 服务实例
    """
    return OSSService()


if __name__ == '__main__':
    import time
    service = get_oss_service()

    test_file = "test.md"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("OSS测试文件")

    try:
        s = time.time()
        url = service.upload_file(test_file)
        e = time.time()
        print(f"用时{e-s}:文件上传成功: {url}")
    except Exception as e:
        print(f"上传失败: {e}")
    finally:
        pass
