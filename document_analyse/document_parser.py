#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   document_parser.py
@Author  :   zemin
@Desc    :   文档解析主逻辑类，文件类型转换、调用paddleocr-vl进行版面解析、返回Markdown文本内容
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dataclasses import dataclass
from typing import Optional, List
from loguru import logger
from document_analyse.file_converter import WordConverter, ConvertResult
from document_analyse.paddle_ocr_vl_parser import PaddleOCRVLParser, ParseResult


@dataclass
class DocumentParseResult:
    """
    文档解析结果数据类
    """
    success: bool
    file_path: str
    file_type: str
    total_pages: int = 0
    pages: Optional[List[ParseResult]] = None


class DocumentParser:
    """
    文档解析工具类
    """
    # 文件类型映射
    WORD_EXTENSIONS = {'.doc', '.docx'}
    PDF_EXTENSIONS = {'.pdf'}
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif', '.webp'}
    TEXT_EXTENSIONS = {'.txt'}
    MARKDOWN_EXTENSIONS = {'.md', '.markdown'}

    def __init__(
        self,
        vl_rec_server_url: str = "http://127.0.0.1:8118/v1",
        vl_rec_max_concurrency: int = 5,
        libreoffice_path: Optional[str] = None,
        use_layout_detection: bool = True,
        use_doc_orientation_classify: bool = False,
        use_doc_unwarping: bool = False,
        use_chart_recognition: bool = True,
        format_block_content: bool = True,
    ):
        self.ocr_parser = PaddleOCRVLParser(
            vl_rec_backend="vllm-server",
            vl_rec_server_url=vl_rec_server_url,
            vl_rec_max_concurrency=vl_rec_max_concurrency,
            use_layout_detection=use_layout_detection,
            use_doc_orientation_classify=use_doc_orientation_classify,
            use_doc_unwarping=use_doc_unwarping,
            use_chart_recognition=use_chart_recognition,
            format_block_content=format_block_content,
        )
        self.word_converter = WordConverter(libreoffice_path=libreoffice_path)

    def _get_file_type(self, file_path: str) -> Optional[str]:
        """
        根据文件扩展名判断文件类型。file_path: 文件路径
        返回文件类型: "word", "pdf", "image", "text", "markdown"，不支持的返回 None
        """
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        if ext in self.WORD_EXTENSIONS:
            return "word"
        elif ext in self.PDF_EXTENSIONS:
            return "pdf"
        elif ext in self.IMAGE_EXTENSIONS:
            return "image"
        elif ext in self.TEXT_EXTENSIONS:
            return "text"
        elif ext in self.MARKDOWN_EXTENSIONS:
            return "markdown"
        else:
            return None

    def _parse_word(self, file_path: str, output_format: str = "markdown") -> DocumentParseResult:
        """
        解析 Word 文件
        file_path: Word文件路径
        output_format: 输出格式 "text" 或 "markdown"
        返回DocumentParseResult对象
        """
        # 尝试转换为 PDF
        convert_result = self.word_converter.convert(file_path, include_table=True)

        if convert_result.success:
            if convert_result.file_type == "pdf":
                # PDF 转换成功，使用 OCR 解析
                logger.info(f"Word 文件已转换为 PDF: {convert_result.file_path}")
                try:
                    parse_results = self.ocr_parser.parse_file(convert_result.file_path)
                    return DocumentParseResult(
                        success=True,
                        file_path=file_path,
                        file_type="word",
                        pages=parse_results,
                        total_pages=len(parse_results)
                    )
                except Exception as e:
                    logger.error(f"OCR 解析 PDF 失败: {e}")
            elif convert_result.file_type == "text":
                # PDF 转换失败，但成功提取了 Word 文本
                logger.info(f"PDF 转换失败，已提取 Word 文本内容")
                # 将文本内容封装为 ParseResult
                parse_results = [
                    ParseResult(
                        page_index=0,
                        text=convert_result.content
                    )
                ]
                return DocumentParseResult(
                    success=True,
                    file_path=file_path,
                    file_type="word",
                    pages=parse_results,
                    total_pages=1
                )

        # 转换和提取都失败
        return DocumentParseResult(
            success=False,
            file_path=file_path,
            file_type="word"
        )

    def _parse_pdf(self, file_path: str, output_format: str = "markdown") -> DocumentParseResult:
        """
        解析PDF文件
        file_path: PDF 文件路径
        output_format: 输出格式 "text" 或 "markdown"
        返回DocumentParseResult 对象
        """
        try:
            parse_results = self.ocr_parser.parse_file(file_path)
            return DocumentParseResult(
                success=True,
                file_path=file_path,
                file_type="pdf",
                pages=parse_results,
                total_pages=len(parse_results)
            )
        except Exception as e:
            logger.error(f"ocr版面解析异常: {e}")
            return DocumentParseResult(
                success=False,
                file_path=file_path,
                file_type="pdf"
            )

    def _parse_image(self, file_path: str, output_format: str = "markdown") -> DocumentParseResult:
        """
        解析图片文件
        file_path: 图片文件路径
        output_format: 输出格式 "text" 或 "markdown"
        返回DocumentParseResult 对象
        """
        try:
            parse_results = self.ocr_parser.parse_file(file_path)
            return DocumentParseResult(
                success=True,
                file_path=file_path,
                file_type="image",
                pages=parse_results,
                total_pages=len(parse_results)
            )
        except Exception as e:
            return DocumentParseResult(
                success=False,
                file_path=file_path,
                file_type="image"
            )

    def _parse_text_file(self, file_path: str, file_type: str) -> DocumentParseResult:
        """
        解析文本文件（TXT、Markdown）
        file_path: 文本文件路径
        file_type: 文件类型 "text" 或 "markdown"
        返回 DocumentParseResult 对象
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 将整个内容作为一页返回
            pages = [
                ParseResult(
                    page_index=0,
                    text=content
                )
            ]
            return DocumentParseResult(
                success=True,
                file_path=file_path,
                file_type=file_type,
                pages=pages,
                total_pages=1
            )
        except UnicodeDecodeError:
            try:
                with open(file_path, "r", encoding="gbk") as f:
                    content = f.read()
                # 将整个内容作为一页返回
                pages = [
                    ParseResult(
                        page_index=0,
                        text=content
                    )
                ]
                return DocumentParseResult(
                    success=True,
                    file_path=file_path,
                    file_type=file_type,
                    pages=pages,
                    total_pages=1
                )
            except Exception as e:
                return DocumentParseResult(
                    success=False,
                    file_path=file_path,
                    file_type=file_type
                )
        except Exception as e:
            return DocumentParseResult(
                success=False,
                file_path=file_path,
                file_type=file_type
            )

    def parse(
        self,
        file_path: str,
        output_format: str = "markdown"
    ) -> DocumentParseResult:
        """
        解析文档
        file_path: 文档文件路径
        output_format: 输出格式
        返回 DocumentParseResult 对象
        """
        if not os.path.exists(file_path):
            return DocumentParseResult(
                success=False,
                file_path=file_path,
                file_type="unknown"
            )

        file_type = self._get_file_type(file_path)
        if not file_type:
            return DocumentParseResult(
                success=False,
                file_path=file_path,
                file_type="unknown"
            )

        logger.info(f"开始解析文件: {file_path} (类型: {file_type})")

        if file_type == "word":
            return self._parse_word(file_path, output_format)
        elif file_type == "pdf":
            return self._parse_pdf(file_path, output_format)
        elif file_type == "image":
            return self._parse_image(file_path, output_format)
        elif file_type == "text":
            return self._parse_text_file(file_path, "text")
        elif file_type == "markdown":
            return self._parse_text_file(file_path, "markdown")

        return DocumentParseResult(
            success=False,
            file_path=file_path,
            file_type=file_type
        )

    def parse_batch(
        self,
        file_paths: List[str],
        output_format: str = "markdown"
    ) -> List[DocumentParseResult]:
        """
        批量解析文档
        file_paths: 文档文件路径列表
        output_format: 输出格式
        返回 DocumentParseResult 对象列表
        """
        results = []
        for file_path in file_paths:
            result = self.parse(file_path, output_format)
            results.append(result)
        return results


if __name__ == "__main__":
    parser = DocumentParser(
        vl_rec_server_url="http://127.0.0.1:8118/v1",
        vl_rec_max_concurrency=5,
        use_layout_detection=True,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_chart_recognition=True,
        format_block_content=True,
    )

    test_files = [
        "/Users/a58/Work/AllCode/PythonCodeAll/MyNLP/ragcheer_20260623/knowledge_base/测试文档.pdf",
    ]

    results = parser.parse_batch(test_files, output_format="markdown")
    