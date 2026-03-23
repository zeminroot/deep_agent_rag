#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   paddle_ocr_vl_parser.py
@Author  :   zemin
@Desc    :   paddle-ocr-vl识别工具,rtx4090平均每页耗时1.46s取决于文本内容长短
'''

import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from paddleocr import PaddleOCRVL
from loguru import logger


@dataclass
class ParseResult:
    """
    文件解析结果数据类
    """
    page_index: int
    text: str


class PaddleOCRVLParser:
    """
    将文件以page为单位解析为Markdown文本，保留原始的排版布局
    """
    SUPPORTED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif', '.webp'}

    def __init__(
        self,
        vl_rec_backend: str = "vllm-server",
        vl_rec_server_url: str = "http://127.0.0.1:8118/v1",
        vl_rec_max_concurrency: int = 5,
        use_layout_detection: bool = True,
        use_doc_orientation_classify: bool = False,
        use_doc_unwarping: bool = False,
        use_chart_recognition: bool = True,
        format_block_content: bool = True,
    ):
        """
        初始化 PaddleOCRVLParser

        Args:
            vl_rec_backend: VLM推理框架，默认为 "vllm-server"
            vl_rec_server_url: VLM部署后的URL接口地址
            vl_rec_max_concurrency: 最大并发数
            use_layout_detection: 是否使用布局检测
            use_doc_orientation_classify: 是否进行方向识别
            use_doc_unwarping: 是否进行图像矫正
            use_chart_recognition: 是否使用图表识别
            format_block_content: 是否格式化块内容
        """
        self.pipeline = PaddleOCRVL(
            vl_rec_backend=vl_rec_backend,
            vl_rec_server_url=vl_rec_server_url,
            vl_rec_max_concurrency=vl_rec_max_concurrency,
            use_layout_detection=use_layout_detection,
            use_doc_orientation_classify=use_doc_orientation_classify,
            use_doc_unwarping=use_doc_unwarping,
            use_chart_recognition=use_chart_recognition,
            format_block_content=format_block_content,
        )

    def _get_file_type(self, file_path: str) -> int:
        """
        根据文件扩展名判断文件类型
        返回 0 表示 PDF 文件，1 表示图片文件
        """
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        if ext == '.pdf':
            return 0
        elif ext in self.SUPPORTED_IMAGE_FORMATS:
            return 1
        else:
            raise ValueError(f"不支持的文件类型: {ext}，支持的格式为: PDF 和 {', '.join(self.SUPPORTED_IMAGE_FORMATS)}")

    def parse_file(
        self,
        file_path: str,
    ) -> List[ParseResult]:
        """
        解析单个文件
        返回解析结果列表，每个元素对应一页:page_index,text
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_type = self._get_file_type(file_path)

        output = self.pipeline.predict(file_path)

        parse_results = []
        for res in output:
            markdown_data = res.markdown
            parse_result = ParseResult(
                page_index=markdown_data.get('page_index', 0),
                text=markdown_data.get('markdown_texts', '')
            )
            parse_results.append(parse_result)

        return parse_results



if __name__ == "__main__":
    parser = PaddleOCRVLParser(
        vl_rec_backend="vllm-server",
        vl_rec_server_url="http://127.0.0.1:8118/v1",
        vl_rec_max_concurrency=5,
        use_layout_detection=True,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_chart_recognition=True,
        format_block_content=True,
    )

    results = parser.parse_file("./1网络诊断专业信息.pdf")

    for result in results:
        print(f"第 {result.page_index} 页: {result.text}")

    print(results)
    print(type(results))
