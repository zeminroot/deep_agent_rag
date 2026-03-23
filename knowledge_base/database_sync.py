#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   database_sync.py
@Author  :   zemin
@Desc    :   mysql数据表操作类
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, update, delete
from document_upload.database_sync import SessionLocal
from document_upload.models import FileRecord
from knowledge_base.models import TextPage, TextChunk, ChunkPage
from loguru import logger


class FileRecordRepositorySync:
    """
    文件记录数据库操作类
    提供对upload_file表的操作接口
    """

    @staticmethod
    def get_unread_files(limit: int = 5000) -> List[FileRecord]:
        """
        获取未读取的文件列表。limit: 最多获取的文件数量
        返回未读取的文件记录列表
        """
        with SessionLocal() as session:
            try:
                # 查询is_read=False的记录，按创建时间升序排序
                stmt = (
                    select(FileRecord)
                    .where(FileRecord.is_read == False)
                    .order_by(FileRecord.created_at.asc())
                    .limit(limit)
                )
                result = session.execute(stmt)
                files = result.scalars().all()
                return files
            except Exception as e:
                logger.error(f"查询未读取文件失败: {e}")
                return []

    @staticmethod
    def mark_as_read(file_id: int) -> bool:
        """
        标记文件为已读取。file_id: 文件ID
        返回是否标记成功
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    update(FileRecord)
                    .where(FileRecord.id == file_id)
                    .values(is_read=True)
                )
                session.execute(stmt)
                session.commit()
                logger.info(f"文件 {file_id} 已标记为已读")
                return True
            except Exception as e:
                logger.error(f"标记文件已读失败: {e}")
                session.rollback()
                return False

    @staticmethod
    def mark_files_as_processing(file_ids: list) -> bool:
        """
        标记文件为处理中（is_read=true），防止其他实例重复处理。file_ids: 文件ID列表
        返回是否标记成功
        """
        with SessionLocal() as session:
            try:
                for file_id in file_ids:
                    stmt = (
                        update(FileRecord)
                        .where(FileRecord.id == file_id)
                        .values(is_read=True)
                    )
                    session.execute(stmt)
                session.commit()
                logger.info(f"已标记 {len(file_ids)} 个文件为处理中")
                return True
            except Exception as e:
                logger.error(f"标记文件为处理中失败: {e}")
                session.rollback()
                return False


class TextPageRepositorySync:
    """
    text_page表数据库操作类
    """

    @staticmethod
    def save_pages(
        file_id: int,
        file_url: str,
        file_total_pages: int,
        pages: List[Dict[str, Any]]
    ) -> List[int]:
        """
        批量保存页面
        file_id: 文件ID
        file_url: 文件URL
        pages: 页面列表，每个元素包含 text, page_index信息
        返回保存的页面ID列表
        """
        page_ids = []
        with SessionLocal() as session:
            try:
                for page_data in pages:
                    text_page = TextPage(
                        page_content=page_data.get('text', ''),
                        page_index=page_data.get('page_index', 0),
                        file_id=file_id,
                        file_url=file_url,
                        file_total_pages=file_total_pages
                    )
                    session.add(text_page)
                    session.flush()  # 获取主键ID
                    page_ids.append(text_page.id)

                session.commit()
                logger.info(f"成功保存 {len(page_ids)} 个页面")
                return page_ids
            except Exception as e:
                logger.error(f"保存页面失败: {e}")
                session.rollback()
                return []

    @staticmethod
    def get_pages_by_file_id(file_id: int) -> List[TextPage]:
        """
        获取指定文件的所有页面
        file_id: 文件ID
        返回页面列表，按page_index升序排列
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(TextPage)
                    .where(TextPage.file_id == file_id)
                    .order_by(TextPage.page_index.asc())
                )
                result = session.execute(stmt)
                pages = result.scalars().all()
                return pages
            except Exception as e:
                logger.error(f"查询文件页面失败: {e}")
                return []

    @staticmethod
    def get_page_by_id(page_id: int) -> Optional[TextPage]:
        """
        根据ID获取单个页面
        page_id: 页面ID
        返回页面对象，不存在则返回None
        """
        with SessionLocal() as session:
            try:
                stmt = select(TextPage).where(TextPage.id == page_id)
                result = session.execute(stmt)
                page = result.scalar_one_or_none()
                return page
            except Exception as e:
                logger.error(f"查询页面失败: {e}")
                return None

    @staticmethod
    def get_page_by_file_and_index(
        file_id: int,
        page_index: int
    ) -> Optional[TextPage]:
        """
        根据文件ID和页面索引获取单个页面
        file_id: 文件ID
        page_index: 页面索引
        返回页面对象，不存在则返回None
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(TextPage)
                    .where(
                        and_(
                            TextPage.file_id == file_id,
                            TextPage.page_index == page_index
                        )
                    )
                )
                result = session.execute(stmt)
                page = result.scalar_one_or_none()
                return page
            except Exception as e:
                logger.error(f"根据文件ID和页面索引查询页面失败: {e}")
                return None

    @staticmethod
    def get_pages_by_indices(
        file_id: int,
        page_indices: List[int]
    ) -> List[TextPage]:
        """
        根据文件ID和页面索引列表批量获取页面
        file_id: 文件ID
        page_indices: 页面索引列表
        返回页面列表，按page_index升序排列
        """
        if not page_indices:
            return []

        with SessionLocal() as session:
            try:
                stmt = (
                    select(TextPage)
                    .where(
                        and_(
                            TextPage.file_id == file_id,
                            TextPage.page_index.in_(page_indices)
                        )
                    )
                    .order_by(TextPage.page_index.asc())
                )
                result = session.execute(stmt)
                pages = result.scalars().all()
                return pages
            except Exception as e:
                logger.error(f"根据页面索引列表查询页面失败: {e}")
                return []


class TextChunkRepositorySync:
    """
    文本块数据库操作类，操作text_chunk表
    """

    @staticmethod
    def save_chunks_for_page(
        page_id: int,
        file_id: int,
        page_index: int,
        chunks: List[Dict[str, Any]]
    ) -> List[int]:
        """
        批量保存页面切分后的文本块
        page_id: 页面ID
        file_id: 文件ID
        page_index: 页面索引
        chunks: 文本块列表，每个元素包含 text, chunk_index
        返回保存的文本块ID列表
        """
        chunk_ids = []
        with SessionLocal() as session:
            try:
                for chunk_data in chunks:
                    text_chunk = TextChunk(
                        chunk_content=chunk_data.get('text', ''),
                        chunk_index=chunk_data.get('chunk_index', 0),
                        file_id=file_id,
                        page_id=page_id,
                        page_index=page_index
                    )
                    session.add(text_chunk)
                    session.flush()  # 获取自增ID
                    chunk_ids.append(text_chunk.id)

                session.commit()
                logger.info(f"成功保存 {len(chunk_ids)} 个文本块")
                return chunk_ids
            except Exception as e:
                logger.error(f"保存文本块失败: {e}")
                session.rollback()
                return []

    @staticmethod
    def get_chunks_by_page_id(page_id: int) -> List[TextChunk]:
        """
        获取指定页面的所有文本块
        page_id: 页面ID
        返回文本块列表，按chunk_index升序排列
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(TextChunk)
                    .where(TextChunk.page_id == page_id)
                    .order_by(TextChunk.chunk_index.asc())
                )
                result = session.execute(stmt)
                chunks = result.scalars().all()
                return chunks
            except Exception as e:
                logger.error(f"查询页面文本块失败: {e}")
                return []

    @staticmethod
    def get_chunks_by_file_id(file_id: int) -> List[TextChunk]:
        """
        获取指定文件的所有文本块
        file_id: 文件ID
        返回文本块列表，按chunk_index升序排列
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(TextChunk)
                    .where(TextChunk.file_id == file_id)
                    .order_by(TextChunk.chunk_index.asc())
                )
                result = session.execute(stmt)
                chunks = result.scalars().all()
                return chunks
            except Exception as e:
                logger.error(f"查询文件文本块失败: {e}")
                return []

    @staticmethod
    def get_chunks_by_file_id_and_indices(
        file_id: int,
        chunk_indices: List[int]
    ) -> List[TextChunk]:
        """
        根据文件ID和文本块索引列表批量获取文本块
        file_id: 文件ID
        chunk_indices: 文本块索引列表
        返回匹配的文本块列表
        """
        if not chunk_indices:
            return []

        with SessionLocal() as session:
            try:
                stmt = (
                    select(TextChunk)
                    .where(
                        and_(
                            TextChunk.file_id == file_id,
                            TextChunk.chunk_index.in_(chunk_indices)
                        )
                    )
                )
                result = session.execute(stmt)
                chunks = result.scalars().all()
                return chunks
            except Exception as e:
                logger.error(f"根据文件ID和索引查询文本块失败: {e}")
                return []

    @staticmethod
    def get_chunk_by_id(chunk_id: int) -> Optional[TextChunk]:
        """
        根据ID获取单个文本块
        chunk_id: 文本块ID
        返回文本块对象，不存在则返回None
        """
        with SessionLocal() as session:
            try:
                stmt = select(TextChunk).where(TextChunk.id == chunk_id)
                result = session.execute(stmt)
                chunk = result.scalar_one_or_none()
                return chunk
            except Exception as e:
                logger.error(f"查询文本块失败: {e}")
                return None

    @staticmethod
    def get_chunk_by_file_and_index(
        file_id: int,
        chunk_index: int
    ) -> Optional[TextChunk]:
        """
        根据文件ID和chunk_index获取单个文本块
        file_id: 文件ID
        chunk_index: 文本块索引
        返回文本块对象，不存在则返回None
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(TextChunk)
                    .where(
                        and_(
                            TextChunk.file_id == file_id,
                            TextChunk.chunk_index == chunk_index
                        )
                    )
                )
                result = session.execute(stmt)
                chunk = result.scalar_one_or_none()
                return chunk
            except Exception as e:
                logger.error(f"根据文件ID和索引查询文本块失败: {e}")
                return None

    @staticmethod
    def get_chunks_by_file_and_page_index(
        file_id: int,
        page_index: int
    ) -> List[TextChunk]:
        """
        根据文件ID和页面索引获取该页面下的所有文本块
        file_id: 文件ID
        page_index: 页面索引
        返回文本块列表，按chunk_index升序排列
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(TextChunk)
                    .where(
                        and_(
                            TextChunk.file_id == file_id,
                            TextChunk.page_index == page_index
                        )
                    )
                    .order_by(TextChunk.chunk_index.asc())
                )
                result = session.execute(stmt)
                chunks = result.scalars().all()
                return chunks
            except Exception as e:
                logger.error(f"根据文件ID和页面索引查询文本块失败: {e}")
                return []


class ChunkPageRepositorySync:
    """
    Chunk与Page关联表数据库操作类
    """

    @staticmethod
    def save_chunk_page_relations(
        file_id: int,
        file_url: str,
        chunk_page_relations: List[Dict[str, Any]]
    ) -> List[int]:
        """
        批量保存chunk和page的关联关系
        file_id: 文件ID
        file_url: 文件URL
        chunk_page_relations: 关联关系列表，每个元素包含chunk_id, chunk_index, page_id, page_index
        返回保存的关联记录ID列表
        """
        chunk_page_ids = []
        with SessionLocal() as session:
            try:
                for relation in chunk_page_relations:
                    chunk_page = ChunkPage(
                        chunk_id=relation.get('chunk_id'),
                        chunk_index=relation.get('chunk_index'),
                        page_id=relation.get('page_id'),
                        page_index=relation.get('page_index'),
                        file_id=file_id,
                        file_url=file_url
                    )
                    session.add(chunk_page)
                    session.flush()  # 获取自增ID
                    chunk_page_ids.append(chunk_page.id)

                session.commit()
                logger.info(f"成功保存 {len(chunk_page_ids)} 个chunk_page关联记录")
                return chunk_page_ids
            except Exception as e:
                logger.error(f"保存chunk_page关联记录失败: {e}")
                session.rollback()
                return []

    @staticmethod
    def get_chunks_by_file_and_page_index(
        file_id: int,
        page_index: int
    ) -> List[Dict[str, Any]]:
        """
        根据文件ID和页面索引获取该页面下的所有chunk关联信息
        file_id: 文件ID
        page_index: 页面索引
        返回chunk关联信息列表，包含chunk_id, chunk_index等
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(ChunkPage)
                    .where(
                        and_(
                            ChunkPage.file_id == file_id,
                            ChunkPage.page_index == page_index
                        )
                    )
                    .order_by(ChunkPage.chunk_index.asc())
                )
                result = session.execute(stmt)
                chunk_pages = result.scalars().all()
                return [
                    {
                        "chunk_id": cp.chunk_id,
                        "chunk_index": cp.chunk_index,
                        "page_id": cp.page_id,
                        "page_index": cp.page_index,
                        "file_id": cp.file_id,
                        "file_url": cp.file_url
                    }
                    for cp in chunk_pages
                ]
            except Exception as e:
                logger.error(f"查询chunk_page关联记录失败: {e}")
                return []

    @staticmethod
    def get_chunk_by_file_and_chunk_index(
        file_id: int,
        chunk_index: int
    ) -> Optional[Dict[str, Any]]:
        """
        根据文件ID和chunk_index获取关联信息
        file_id: 文件ID
        chunk_index: 文本块索引
        返回chunk关联信息，包含chunk_id, page_id等
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(ChunkPage)
                    .where(
                        and_(
                            ChunkPage.file_id == file_id,
                            ChunkPage.chunk_index == chunk_index
                        )
                    )
                )
                result = session.execute(stmt)
                cp = result.scalar_one_or_none()
                if cp:
                    return {
                        "chunk_id": cp.chunk_id,
                        "chunk_index": cp.chunk_index,
                        "page_id": cp.page_id,
                        "page_index": cp.page_index,
                        "file_id": cp.file_id,
                        "file_url": cp.file_url
                    }
                return None
            except Exception as e:
                logger.error(f"查询chunk_page关联记录失败: {e}")
                return None

    @staticmethod
    def get_chunks_by_page_id(page_id: int) -> List[Dict[str, Any]]:
        """
        根据页面ID获取该页面下的所有chunk关联信息
        page_id: 页面ID
        返回chunk关联信息列表
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(ChunkPage)
                    .where(ChunkPage.page_id == page_id)
                    .order_by(ChunkPage.chunk_index.asc())
                )
                result = session.execute(stmt)
                chunk_pages = result.scalars().all()
                return [
                    {
                        "chunk_id": cp.chunk_id,
                        "chunk_index": cp.chunk_index,
                        "page_id": cp.page_id,
                        "page_index": cp.page_index,
                        "file_id": cp.file_id,
                        "file_url": cp.file_url
                    }
                    for cp in chunk_pages
                ]
            except Exception as e:
                logger.error(f"根据page_id查询chunk_page关联记录失败: {e}")
                return []
