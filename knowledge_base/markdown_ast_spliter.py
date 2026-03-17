#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   markdown_chunker_spliter.py
@Author  :   zemin
@Desc    :   使用AST语法分析树进行Markdown文本切分，最大成都保存保留文本块语义完整性
'''

from markdown_it import MarkdownIt
from typing import List, Tuple


class MarkdownAstExtractor:
    """
    使用ast语法树获取Markdown原始文本块，对图表、表格、html保留完整文本块，对过长纯文本块内容滑动窗口切分
    """
    def __init__(self, chunk_max_len=1000, overlap_len=150):
        self.md = MarkdownIt()
        self.chunk_max_len = chunk_max_len
        self.overlap_len = overlap_len

    @staticmethod
    def _split_long_text(text: str, chunk_size: int, overlap: int) -> List[str]:
        """
        超长文本切分
        1. 先按换行符切分，保留行结构
        2. 单行长度 ≤ chunk_size：直接保留
        3. 单行长度 > chunk_size：对该行执行滑动窗口切分
        """
        chunks = []
        lines = text.split('\n')
        for line in lines:
            if not line.strip():
                continue
            
            line_len = len(line)
            if line_len <= chunk_size:
                chunks.append(line)
            else:
                step = chunk_size - overlap
                start = 0
                while start < line_len:
                    end = start + chunk_size
                    chunks.append(line[start:end])
                    start += step
        
        return chunks

    def extract_blocks(self, markdown_text: str) -> List[Tuple[str, str]]:
        """
        使用ast语法树获取文本块和文本块类型
        """
        lines = markdown_text.splitlines()
        tokens = self.md.parse(markdown_text)
        blocks = []

        for token in tokens:
            # 跳过无内容的段落块开始和结束标签
            if token.type.endswith("_open") or token.type.endswith("_close"):
                continue
            if not token.map or not token.content.strip():
                continue

            # 截取原始文本，保留所有Markdown语法
            start_line, end_line = token.map
            raw_block_lines = lines[start_line:end_line]
            raw_content = "\n".join(raw_block_lines).strip()
            if not raw_content:
                continue

            blocks.append((token.type, raw_content))

        return blocks

    def extract_chunks(self, markdown_text: str) -> List[str]:
        """
        解析的到chunk列表
        """
        blocks = self.extract_blocks(markdown_text)
        chunks = []
        for block_type, content in blocks:
            if len(content) > self.chunk_max_len:
                # 仅inline类型执行切分，其他块完整保留
                if block_type == "inline":
                    chunks.extend(self._split_long_text(content, self.chunk_max_len, self.overlap_len))
                else:
                    chunks.append(content)
            else:
                chunks.append(content)
        return chunks


