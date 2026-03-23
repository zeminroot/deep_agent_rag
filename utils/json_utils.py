#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   json_utils.py
@Author  :   zemin
@Desc    :   JSON 工具函数
'''


def fix_json_string(json_str: str) -> str:
    """
    尝试修复常见的 JSON 格式问题，特别是中文引号未转义的问题

    Args:
        json_str: 可能包含格式问题的 JSON 字符串

    Returns:
        修复后的 JSON 字符串
    """
    # 移除首尾空白
    json_str = json_str.strip()

    # 修复中文引号问题：将字符串内的中文双引号替换为转义的英文引号
    result = []
    i = 0
    n = len(json_str)

    while i < n:
        if json_str[i] == '"':
            # 找到 JSON 字符串结束位置 转义
            j = i + 1
            while j < n:
                if json_str[j] == '\\' and j + 1 < n:
                    j += 2  # 跳过转义字符
                elif json_str[j] == '"':
                    break
                else:
                    j += 1

            # 提取字符串内容
            content = json_str[i+1:j]
            # 将内容中的中文引号替换为转义的英文引号
            content = content.replace('"', '\\"').replace('"', '\\"')
            result.append('"' + content + '"')
            i = j + 1
        else:
            result.append(json_str[i])
            i += 1

    return ''.join(result)
