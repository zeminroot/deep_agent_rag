#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    :   url_utils.py
@Author  :   zemin
@Desc    :   URL相关工具函数
"""
from urllib.parse import unquote


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
