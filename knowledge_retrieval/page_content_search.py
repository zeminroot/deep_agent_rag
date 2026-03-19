#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   page_content_search.py
@Author  :   zemin
@Desc    :   页面内容搜索，根据文件ID和页面索引搜索页面内容
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import List, Dict, Any, Optional
from loguru import logger
from knowledge_base.database import TextPageRepository
from knowledge_base.models import TextPage
from urllib.parse import unquote



class PageContentSearch:
    def __init__(self):
        pass
    

    async def get_oss_original_filename(self, oss_url):
        """
        从OSS地址提取原始文件名（含后缀）
        param oss_url: 阿里云OSS文件完整URL
        return: 解码后的原始文件名
        """
        file_part = oss_url.rsplit('/', 1)[-1]
        encoded_filename = file_part.split('-', 1)[-1]
        original_filename = unquote(encoded_filename)
        return original_filename


    async def get_multiple_pages(
        self,
        file_id: int,
        page_indices: List[int],
    ) -> Dict[str, Any]:
        """
        获取指定文件指定页面的内容

        Args:
            file_id: 文件ID
            page_indices: 要获取的页面索引列表

        Returns:
            获取页面信息后组装的文本
        """
        try:
            # 获取该文件下的所有页面
            all_pages = await TextPageRepository.get_pages_by_file_id(file_id)

            if not all_pages:
                logger.warning(f"文件 {file_id} 中没有页面数据")
                return {
                    "error": f"file_id: {file_id}。该文件中没有页面数据"
                }

            # 找到目标pages
            target_pages_info = []
            for target_page_index in page_indices:
                for page in all_pages:
                    if page.page_index == target_page_index:
                        file_name = await self.get_oss_original_filename(oss_url=page.file_url)
                        target_pages_info.append({
                            "page_id": page.id,
                            "page_content": page.page_content,
                            "page_index": page.page_index,
                            "file_id": page.file_id,
                            "file_name": file_name,
                            "file_total_pages":page.file_total_pages
                        })
                    else:
                        continue
                    
            # 将查找到的全部页面组装为统一文本
            wenjian_name = ""
            wenjian_id = None
            total_pages_num = None
            pages_content = ""
            if target_pages_info:
                first_page = target_pages_info[0]
                wenjian_name = first_page["file_name"]
                wenjian_id = first_page["file_id"]
                total_pages_num = first_page["file_total_pages"]
                
                p_content_list = []
                for p_info in target_pages_info:
                    p_content_list.append(f"--- 第 {p_info['page_index']} 页 (page_index:{p_info['page_index']})---\n{p_info['page_content']}")
                pages_content = "\n".join(p_content_list)
            else:
                pages_content = "未获取到对应页面内容"
                
            final_text = f"\nfile_name:{wenjian_name}\nfile_id:{wenjian_id}\n文件总页数:{total_pages_num}\n页面内容:\n{pages_content}\n\n\n"
            return final_text
                
        except Exception as e:
            logger.error(f"获取页面内容失败: {e}")
            return f"获取页面内容失败"


