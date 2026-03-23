#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   file_downloader.py
@Author  :   zemin
@Desc    :   根据url下载文件
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tempfile
from typing import Optional
from urllib.parse import urlparse
from loguru import logger
import requests


class FileDownloader:
    """
    使用 requests 直接下载公共URL的文件
    """

    def __init__(self, timeout: int = 300):
        self.timeout = timeout
        logger.info(f"文件下载器初始化完成: timeout={timeout}秒")


    def _get_filename_from_url(self, url: str) -> str:
        """
        从URL中提取文件名，返回文件名
        """
        try:
            parsed = urlparse(url)
            path = parsed.path
            # 获取文件名
            filename = os.path.basename(path)
            # 如果没有文件名，使用默认名称
            if not filename:
                filename = f"downloaded_file_{id(url)}.tmp"
            return filename
        except Exception as e:
            logger.warning(f"从URL提取文件名失败: {e}，使用默认文件名")
            return f"downloaded_file_{id(url)}.tmp"


    def download_file(self, url: str) -> Optional[str]:
        """
        下载文件到本地临时目录
        url: 文件URL
        返回本地临时文件路径，下载失败返回None
        """
        try:
            logger.info(f"开始下载文件: {url}")

            response = requests.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status() 

            # 获取文件名
            filename = self._get_filename_from_url(url)
            temp_file = os.path.join(tempfile.gettempdir(), filename)

            # 写入文件
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    # 分块下载，块大小1M
                    if chunk:  # 过滤掉keep-alive的空chunk
                        f.write(chunk)

            file_size = os.path.getsize(temp_file)
            logger.info(f"文件下载成功: {temp_file} ({file_size/(1024*1024)} M)")
            return temp_file

        except requests.RequestException as e:
            logger.error(f"文件下载失败: {e}")
            return None
        except Exception as e:
            logger.error(f"文件下载失败: {e}")
            return None


if __name__ == "__main__":
    downloader = FileDownloader()

    test_url = "https://agenticrag-data.oss-cn-beijing.aliyuncs.com/uploads/43afc986f30fc4f4b0.png"

    local_path = downloader.download_file(test_url)
    if local_path:
        print(f"文件已下载到: {local_path}")
        if os.path.exists(local_path):
            os.remove(local_path)
            print(f"文件已删除")
    else:
        print("文件下载失败")