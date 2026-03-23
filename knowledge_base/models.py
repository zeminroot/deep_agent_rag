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

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    page_content = Column(
        Text,
        nullable=False,
        comment="页面文本内容"
    )

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
    
    file_total_pages = Column(
        Integer,
        nullable=False,
        comment="页面所在文件的总页数"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间"
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间"
    )

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
        返回包含页面信息的字典
        """
        return {
            "id": self.id,
            "page_content": self.page_content,
            "page_index": self.page_index,
            "file_id": self.file_id,
            "file_url": self.file_url,
            "file_total_pages": self.file_total_pages,
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

    # 关联文件ID，外键关联upload_file表
    file_id = Column(
        Integer,
        ForeignKey('upload_file.id', ondelete='CASCADE'),
        nullable=False,
        comment="关联的文件ID"
    )

    # 关联页面ID，外键关联text_page表
    page_id = Column(
        Integer,
        ForeignKey('text_page.id', ondelete='CASCADE'),
        nullable=False,
        comment="关联的页面ID"
    )

    # 页面索引，方便直接查询
    page_index = Column(
        Integer,
        nullable=False,
        comment="页面索引，用于快速查询"
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
        # file_id和chunk_index联合索引，高效查询文件中的特定文本块
        Index('idx_text_chunk_file_chunk', 'file_id', 'chunk_index'),
        # file_id和page_index联合索引，查询文件特定页面的所有chunk
        Index('idx_text_chunk_file_page', 'file_id', 'page_index'),
        {'comment': '文本块表 - 存储页面切分后的文本块信息'}
    )

    def __repr__(self):
        """
        对象字符串表示
        """
        return f"<TextChunk(id={self.id}, file_id={self.file_id}, page_id={self.page_id}, chunk_index={self.chunk_index})>"

    def to_dict(self):
        """
        将对象转换为字典格式
        返回包含文本块信息的字典
        """
        return {
            "id": self.id,
            "chunk_content": self.chunk_content,
            "chunk_index": self.chunk_index,
            "page_id": self.page_id,
            "page_index": self.page_index,
            "file_id": self.file_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ChunkPage(Base):
    """
    Chunk与Page关联表
    建立chunk和page之间的关联关系，支持通过file_id+page_index快速查询关联的chunk信息
    """
    __tablename__ = "chunk_page"

    # 主键ID
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    # 关联的chunk ID
    chunk_id = Column(
        Integer,
        ForeignKey('text_chunk.id', ondelete='CASCADE'),
        nullable=False,
        comment="关联的文本块ID"
    )

    # chunk在整个文件中的索引
    chunk_index = Column(
        Integer,
        nullable=False,
        comment="文本块在整个文件里的索引"
    )

    # 关联的page ID
    page_id = Column(
        Integer,
        ForeignKey('text_page.id', ondelete='CASCADE'),
        nullable=False,
        comment="关联的页面ID"
    )

    # page在整个文件中的索引
    page_index = Column(
        Integer,
        nullable=False,
        comment="页面在文件里的索引"
    )

    # 关联的文件ID
    file_id = Column(
        Integer,
        ForeignKey('upload_file.id', ondelete='CASCADE'),
        nullable=False,
        comment="关联的文件ID"
    )

    # 文件URL
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

    __table_args__ = (
        # file_id和chunk_index联合索引，通过file_id+chunk_index快速查找chunk
        Index('idx_chunk_page_file_chunk', 'file_id', 'chunk_index'),
        # file_id和page_index联合索引，通过file_id+page_index快速查找该页面下的所有chunk
        Index('idx_chunk_page_file_page', 'file_id', 'page_index'),
        # page_id索引，通过page_id查询关联的chunks
        Index('idx_chunk_page_page_id', 'page_id'),
        # chunk_id索引，通过chunk_id查询关联信息
        Index('idx_chunk_page_chunk_id', 'chunk_id'),
        {'comment': 'Chunk与Page关联表 - 建立chunk和page之间的关联关系'}
    )

    def __repr__(self):
        """
        对象的字符串表示
        """
        return f"<ChunkPage(id={self.id}, file_id={self.file_id}, chunk_id={self.chunk_id}, page_id={self.page_id}, chunk_index={self.chunk_index}, page_index={self.page_index})>"

    def to_dict(self):
        """
        将对象转换为字典格式
        返回包含关联信息的字典
        """
        return {
            "id": self.id,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "page_id": self.page_id,
            "page_index": self.page_index,
            "file_id": self.file_id,
            "file_url": self.file_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }