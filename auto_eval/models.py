#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   models.py
@Author  :   zemin
@Desc    :   RAG评测数据表结构
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import Column, Integer, String, Text, DateTime, Index, JSON
from sqlalchemy.sql import func
from document_upload.database import Base


class EvalQA(Base):
    """
    RAG评测QA表，存储生成的评测问题和答案
    """
    __tablename__ = "eval_qa"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    question = Column(
        Text,
        nullable=False,
        comment="问题内容"
    )

    answer = Column(
        Text,
        nullable=False,
        comment="答案内容"
    )

    file_id = Column(
        Integer,
        nullable=False,
        comment="关联的文件ID"
    )

    chunk_index_list = Column(
        JSON,
        nullable=False,
        comment="答案来源的chunk_index列表"
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
        # file_id添加索引
        Index('idx_eval_qa_file_id', 'file_id'),
        # 创建时间索引，用于拉取最新记录
        Index('idx_eval_qa_created_at', 'created_at'),
        {'comment': 'RAG评测QA表，存储生成的评测问题和答案'}
    )

    def __repr__(self):
        return f"<EvalQA(id={self.id}, file_id={self.file_id}, question={self.question[:30]}...)>"

    def to_dict(self):
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "file_id": self.file_id,
            "chunk_index_list": self.chunk_index_list,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EvalResult(Base):
    """
    RAG评测结果表，存储评测任务的执行结果
    """
    __tablename__ = "eval_result"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    qa_id = Column(
        Integer,
        nullable=False,
        comment="关联的eval_qa表记录ID"
    )

    chat_answer = Column(
        Text,
        nullable=False,
        comment="chat接口返回的答案"
    )

    retrieved_chunks = Column(
        JSON,
        nullable=False,
        comment="召回的chunk信息列表"
    )

    recall_accuracy = Column(
        Integer,
        nullable=False,
        comment="召回准确率，百分比(0-100)"
    )

    fact_consistency_score = Column(
        Integer,
        nullable=False,
        comment="事实一致性得分(0-1)"
    )

    completeness_score = Column(
        Integer,
        nullable=False,
        comment="完整性得分(0-1)"
    )

    total_score = Column(
        Integer,
        nullable=False,
        comment="总得分(0-2)"
    )

    batch_id = Column(
        String(64),
        nullable=False,
        comment="评测任务批次ID"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间"
    )

    __table_args__ = (
        # batch_id添加索引
        Index('idx_eval_result_batch_id', 'batch_id'),
        # qa_id添加索引
        Index('idx_eval_result_qa_id', 'qa_id'),
        {'comment': 'RAG评测结果表 - 存储评测任务的执行结果'}
    )

    def __repr__(self):
        return f"<EvalResult(id={self.id}, qa_id={self.qa_id}, total_score={self.total_score})>"

    def to_dict(self):
        return {
            "id": self.id,
            "qa_id": self.qa_id,
            "chat_answer": self.chat_answer,
            "retrieved_chunks": self.retrieved_chunks,
            "recall_accuracy": self.recall_accuracy,
            "fact_consistency_score": self.fact_consistency_score,
            "completeness_score": self.completeness_score,
            "total_score": self.total_score,
            "batch_id": self.batch_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
