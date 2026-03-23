#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   models.py
@Author  :   zemin
@Desc    :   定义数据表结构
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index
from sqlalchemy.sql import func
from datetime import datetime
from document_upload.database import Base


class FileRecord(Base):
    """
    文件记录表，存储用户上传的文件信息
    """
    
    __tablename__ = "upload_file"  # mysql表名

    # 主键ID，自增
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    # 用户ID
    user_id = Column(
        String(64),
        nullable=False,
        comment="用户ID"
    )

    # 文件URL，OSS上文件的访问地址
    file_url = Column(
        String(512),
        nullable=False,
        comment="文件URL地址"
    )

    # 是否已读，标记文件是否被处理/读取过
    is_read = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否已读"
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

    # 给is_read字段添加索引
    __table_args__ = (
        Index('idx_is_read', 'is_read'),
        {'comment': '文件记录表 - 存储用户上传的文件信息'}
    )

    def __repr__(self):
        """
        对象的字符串表示
        """
        return f"<FileRecord(id={self.id}, user_id='{self.user_id}', file_url='{self.file_url}', is_read={self.is_read})>"

    def to_dict(self):
        """
        将对象转换为字典格式。dict: 包含文件记录信息的字典
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "file_url": self.file_url,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
