#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   text_chunker.py
@Author  :   zemin
@Desc    :   文本切分工具类
对ParseResult数据类的页面内容的到文本块列表
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import get_settings
from document_analyse.paddle_ocr_vl_parser import ParseResult
from typing import Optional, Dict, List, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from knowledge_base.markdown_ast_spliter import MarkdownAstExtractor
from loguru import logger


class DocumentTextChunker:
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
    ):
        """
        初始化切分器参数

        Args:
            chunk_size: 切分块的字符长度（默认1000）
            chunk_overlap: 块之间的重叠字符长度（避免语义断裂，默认100）
        """
        self.settings = get_settings()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
            ("####", "Header 4"),
            ("#####", "Header 5"),
            ("######", "Header 6")
        ]

        self.separators = ["\n\n", "\n", " ", ""]  # 分层分割策略
        self.ast_extractor = MarkdownAstExtractor(chunk_max_len=self.chunk_size, overlap_len=self.chunk_overlap)
        self.recursive_splitter = RecursiveCharacterTextSplitter(chunk_size=self.chunk_size, 
                                                                 chunk_overlap=self.chunk_overlap, 
                                                                 separators=self.separators)
        
        self.markdown_header_spliter = MarkdownHeaderTextSplitter(headers_to_split_on=self.headers_to_split_on, 
                                                                  return_each_line=True,
                                                                  strip_headers=False)
        

    def split_pages(
        self,
        pages: List[ParseResult],
        split_mode: str = "markdown_ast",
        file_chunks_num: int = None
    ) -> List[Dict[str, Any]]:
        """
        对页面直接进行多模式切分

        Args:
            pages: 页面列表[{page_index, text}, {page_index, text}]
            split_mode: 切分模式：
                - "recursive"：RecursiveCharacterTextSplitter 通用字符切分
                - "markdown_header"：MarkdownHeaderTextSplitter 按标题切分
                - "markdown_then_recursive"：先按标题切分再递归字符切分
                - "markdown_ast"：使用AST语法分析树进行Markdown文本切分（最大保留文本块语义完整性）

        Returns:
            切分后的块列表，每个块包含文本、块索引、所在页面索引
            [{
                "chunk_index": 0,
                "text": "文本内容",
                "page_index": 0
            }]
        """
        split_chunks = []

        # 遍历每个页面切分
        for page in pages:
            page_text = page.text
            page_index = page.page_index

            # 模式1：通用递归字符切分
            if split_mode == "recursive":
                chunks = self.recursive_splitter.split_text(page_text)
                # 封装结果
                for i, chunk_text in enumerate(chunks):
                    split_chunks.append({
                        "chunk_index": file_chunks_num+len(split_chunks),
                        "text": chunk_text,
                        "page_index": page_index
                    })

            # 模式2：按Markdown标题切分（按H1/H2/H3拆分）
            elif split_mode == "markdown_header":
                md_chunks = self.markdown_header_spliter.split_text(page_text)
                # 封装结果
                for md_chunk in md_chunks:
                    split_chunks.append({
                        "chunk_index": file_chunks_num+len(split_chunks),
                        "text": md_chunk.page_content,
                        "page_index": page_index,
                    })

            # 模式3：组合切分（先按标题切分，再递归字符切分）
            elif split_mode == "markdown_then_recursive":
                # 1按标题分割
                md_header_docs = self.markdown_header_spliter.split_text(page_text)
                logger.success(f"使用标题切分的结果: \n{md_header_docs}")

                # 2对每个header chunk递归分割
                for md_header_doc in md_header_docs:
                    doc_text = md_header_doc.page_content if md_header_doc.page_content else ""
                    sub_chunks = self.recursive_splitter.split_text(doc_text)

                    # 封装每个子 chunk
                    for sub_chunk in sub_chunks:
                        split_chunks.append({
                            "chunk_index": file_chunks_num+len(split_chunks),
                            "text": sub_chunk,
                            "page_index": page_index,
                        })
                logger.success(f"按标题切分后二次递归切分的结果: \n{split_chunks}")

            # 模式4：使用AST语法分析树分块+滑动窗口切分
            elif split_mode == "markdown_ast":
                chunks = self.ast_extractor.extract_chunks(page_text)
                for i, chunk_text in enumerate(chunks):
                    split_chunks.append({
                        "chunk_index": file_chunks_num+len(split_chunks),
                        "text": chunk_text,
                        "page_index": page_index
                    })
                logger.success(f"使用AST切分的结果: \n{split_chunks}")

            else:
                raise ValueError(
                    f"不支持的切分模式：{split_mode}，可选：recursive/markdown_header/markdown_then_recursive/markdown_ast"
                )

        return split_chunks
