#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   database.py
@Author  :   zemin
@Desc    :   mysql数据表操作类
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, delete
from document_upload.database import AsyncSessionLocal
from document_upload.models import FileRecord
from knowledge_base.models import TextPage, TextChunk
from loguru import logger


class FileRecordRepository:
    """
    文件记录数据库操作类
    提供对upload_file表的操作接口
    """
    
    @staticmethod
    async def get_unread_files(limit: int = 5000) -> List[FileRecord]:
        """
        获取未读取的文件列表

        Args:
            limit: 最多获取的文件数量

        Returns:
            未读取的文件记录列表
        """
        async with AsyncSessionLocal() as session:
            try:
                # 查询is_read=False的记录，按创建时间升序排序
                stmt = (
                    select(FileRecord)
                    .where(FileRecord.is_read == False)
                    .order_by(FileRecord.created_at.asc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                files = result.scalars().all()
                return files
            except Exception as e:
                logger.error(f"查询未读取文件失败: {e}")
                return []

    @staticmethod
    async def mark_as_read(file_id: int) -> bool:
        """
        标记文件为已读取

        Args:
            file_id: 文件ID

        Returns:
            是否标记成功
        """
        async with AsyncSessionLocal() as session:
            try:
                stmt = (
                    update(FileRecord)
                    .where(FileRecord.id == file_id)
                    .values(is_read=True)
                )
                await session.execute(stmt)
                await session.commit()
                logger.info(f"文件 {file_id} 已标记为已读")
                return True
            except Exception as e:
                logger.error(f"标记文件已读失败: {e}")
                await session.rollback()
                return False


class TextPageRepository:
    """
    text_page表数据库操作类
    """

    @staticmethod
    async def save_pages(
        file_id: int,
        file_url: str,
        pages: List[Dict[str, Any]]
    ) -> List[int]:
        """
        批量保存页面

        Args:
            file_id: 文件ID
            file_url: 文件URL
            pages: 页面列表，每个元素包含 text, page_index信息

        Returns:
            保存的页面ID列表
        """
        page_ids = []
        async with AsyncSessionLocal() as session:
            try:
                for page_data in pages:
                    text_page = TextPage(
                        page_content=page_data.get('text', ''),
                        page_index=page_data.get('page_index', 0),
                        file_id=file_id,
                        file_url=file_url
                    )
                    session.add(text_page)
                    await session.flush()  # 获取主键ID
                    page_ids.append(text_page.id)

                await session.commit()
                logger.info(f"成功保存 {len(page_ids)} 个页面")
                return page_ids
            except Exception as e:
                logger.error(f"保存页面失败: {e}")
                await session.rollback()
                return []

    @staticmethod
    async def get_pages_by_file_id(file_id: int) -> List[TextPage]:
        """
        获取指定文件的所有页面

        Args:
            file_id: 文件ID

        Returns:
            页面列表，按page_index升序排列
        """
        async with AsyncSessionLocal() as session:
            try:
                stmt = (
                    select(TextPage)
                    .where(TextPage.file_id == file_id)
                    .order_by(TextPage.page_index.asc())
                )
                result = await session.execute(stmt)
                pages = result.scalars().all()
                return pages
            except Exception as e:
                logger.error(f"查询文件页面失败: {e}")
                return []

    @staticmethod
    async def get_page_by_id(page_id: int) -> Optional[TextPage]:
        """
        根据ID获取单个页面

        Args:
            page_id: 页面ID

        Returns:
            页面对象，不存在则返回None
        """
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(TextPage).where(TextPage.id == page_id)
                result = await session.execute(stmt)
                page = result.scalar_one_or_none()
                return page
            except Exception as e:
                logger.error(f"查询页面失败: {e}")
                return None


class TextChunkRepository:
    """
    文本块数据库操作类，操作text_chunk表
    """

    @staticmethod
    async def save_chunks_for_page(
        page_id: int,
        chunks: List[Dict[str, Any]]
    ) -> List[int]:
        """
        批量保存页面切分后的文本块

        Args:
            page_id: 页面ID
            chunks: 文本块列表，每个元素包含 text, chunk_index 等信息

        Returns:
            保存的文本块ID列表
        """
        chunk_ids = []
        async with AsyncSessionLocal() as session:
            try:
                for chunk_data in chunks:
                    text_chunk = TextChunk(
                        chunk_content=chunk_data.get('text', ''),
                        chunk_index=chunk_data.get('chunk_index', 0),
                        page_id=page_id
                    )
                    session.add(text_chunk)
                    await session.flush()  # 获取自增ID
                    chunk_ids.append(text_chunk.id)

                await session.commit()
                logger.info(f"成功保存 {len(chunk_ids)} 个文本块")
                return chunk_ids
            except Exception as e:
                logger.error(f"保存文本块失败: {e}")
                await session.rollback()
                return []

    @staticmethod
    async def get_chunks_by_page_id(page_id: int) -> List[TextChunk]:
        """
        获取指定页面的所有文本块

        Args:
            page_id: 页面ID

        Returns:
            文本块列表，按chunk_index升序排列
        """
        async with AsyncSessionLocal() as session:
            try:
                stmt = (
                    select(TextChunk)
                    .where(TextChunk.page_id == page_id)
                    .order_by(TextChunk.chunk_index.asc())
                )
                result = await session.execute(stmt)
                chunks = result.scalars().all()
                return chunks
            except Exception as e:
                logger.error(f"查询页面文本块失败: {e}")
                return []

    @staticmethod
    async def get_chunks_by_file_id(file_id: int) -> List[TextChunk]:
        """
        获取指定文件的所有文本块

        Args:
            file_id: 文件ID

        Returns:
            文本块列表，按chunk_index升序排列
        """
        async with AsyncSessionLocal() as session:
            try:
                # 获取该文件的所有页面
                stmt = (
                    select(TextPage)
                    .where(TextPage.file_id == file_id)
                    .order_by(TextPage.page_index.asc())
                )
                result = await session.execute(stmt)
                pages = result.scalars().all()

                # 获取所有页面的文本块
                all_chunks = []
                for page in pages:
                    chunks = await TextChunkRepository.get_chunks_by_page_id(page.id)
                    all_chunks.extend(chunks)

                return all_chunks
            except Exception as e:
                logger.error(f"查询文件文本块失败: {e}")
                return []

    @staticmethod
    async def get_chunk_by_id(chunk_id: int) -> Optional[TextChunk]:
        """
        根据ID获取单个文本块

        Args:
            chunk_id: 文本块ID

        Returns:
            文本块对象，不存在则返回None
        """
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(TextChunk).where(TextChunk.id == chunk_id)
                result = await session.execute(stmt)
                chunk = result.scalar_one_or_none()
                return chunk
            except Exception as e:
                logger.error(f"查询文本块失败: {e}")
                return None
