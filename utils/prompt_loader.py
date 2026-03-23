#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    :   prompt_loader.py
@Author  :   zemin
@Desc    :   Prompt文件加载工具
"""

import os


def load_prompt(file_path: str, **kwargs) -> str:
    """
    从指定路径加载并格式化prompt内容
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Prompt文件不存在: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if kwargs:
        try:
            content = content.format(**kwargs)
        except KeyError as e:
            raise KeyError(f"Prompt缺少必要的变量: {e}")

    return content
