#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   models.py
@Author  :   zemin
@Desc    :   数据表模型，文本页tetx_page表，text_chunk表
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import Column, Integer, String, Text, DateTime, Index, ForeignKey
from sqlalchemy.sql import func
from document_upload.database import Base


class TextPage(Base):
    """
    文本页表，存储文档解析后的页面信息，每个页面对应原始文档的一页
    """

    __tablename__ = "text_page"

    # 主键ID
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    # 页面内容
    page_content = Column(
        Text,
        nullable=False,
        comment="页面文本内容"
    )

    # 页面索引
    page_index = Column(
        Integer,
        nullable=False,
        comment="页面索引"
    )

    # 关联文件记录ID，外键关联upload_file表
    file_id = Column(
        Integer,
        ForeignKey('upload_file.id', ondelete='CASCADE'),
        nullable=False,
        comment="关联的文件ID"
    )

    # 文件URL OSS地址
    file_url = Column(
        String(512),
        nullable=False,
        comment="文件URL地址"
    )

    # 创建时间
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间"
    )

    # 更新时间
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间"
    )

    # 为查询添加索引，提高查询效率
    __table_args__ = (
        # 添加file_id为索引
        Index('idx_text_page_file_id', 'file_id'),
        # 添加file_id和page_index的联合索引
        Index('idx_text_page_file_page', 'file_id', 'page_index'),
        {'comment': '文本页表 - 存储文档解析后的页面信息'}
    )

    def __repr__(self):
        """
        对象的字符串表示
        """
        return f"<TextPage(id={self.id}, file_id={self.file_id}, page_index={self.page_index})>"

    def to_dict(self):
        """
        将对象转换为字典格式

        Returns:
            dict: 包含页面信息的字典
        """
        return {
            "id": self.id,
            "page_content": self.page_content,
            "page_index": self.page_index,
            "file_id": self.file_id,
            "file_url": self.file_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TextChunk(Base):
    """
    文本块表，关联text_page表
    存储页面切分后的文本块，每个文本块关联到所在page的id
    """
    __tablename__ = "text_chunk"

    # 主键ID
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    # 文本块内容
    chunk_content = Column(
        Text,
        nullable=False,
        comment="文本块内容"
    )

    # 文本块在整个文件中的索引
    chunk_index = Column(
        Integer,
        nullable=False,
        comment="文本块在整个文件里的索引"
    )

    # 关联页面ID，外键关联text_page表
    page_id = Column(
        Integer,
        ForeignKey('text_page.id', ondelete='CASCADE'),
        nullable=False,
        comment="关联的页面ID"
    )

    # 创建时间
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间"
    )

    # 更新时间
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间"
    )

    __table_args__ = (
        # page_id添加索引，按页面查询文本块
        Index('idx_text_chunk_page_id', 'page_id'),
        # page_id和chunk_index联合索引，查询某个页面的所有文本块，按dhunk_index排序
        Index('idx_text_chunk_page_chunk', 'page_id', 'chunk_index'),
        {'comment': '文本块表 - 存储页面切分后的文本块信息'}
    )

    def __repr__(self):
        """
        对象字符串表示
        """
        return f"<TextChunk(id={self.id}, page_id={self.page_id}, chunk_index={self.chunk_index})>"

    def to_dict(self):
        """
        将对象转换为字典格式

        Returns:
            dict: 包含文本块信息的字典
        """
        return {
            "id": self.id,
            "chunk_content": self.chunk_content,
            "chunk_index": self.chunk_index,
            "page_id": self.page_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }