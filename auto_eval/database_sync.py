#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   database_sync.py
@Author  :   zemin
@Desc    :   RAG评测数据库操作类（同步版本）
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, func as sql_func
from datetime import datetime, timedelta
from document_upload.database_sync import SessionLocal
from knowledge_base.models import TextChunk
from auto_eval.models import EvalQA, EvalResult
from knowledge_base.models import TextPage

from loguru import logger


class EvalQARepositorySync:
    """
    eval_qa表数据库操作类
    """

    @staticmethod
    def get_yesterday_chunks() -> List[TextChunk]:
        """
        获取前一天新增的文本块，返回前一天创建的文本块列表
        """
        now = datetime.now()
        yesterday_start = now - timedelta(days=1)
        yesterday_start = yesterday_start.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_start.replace(hour=23, minute=59, second=59)

        with SessionLocal() as session:
            try:
                stmt = (
                    select(TextChunk)
                    .where(
                        and_(
                            TextChunk.created_at >= yesterday_start,
                            TextChunk.created_at <= yesterday_end
                        )
                    )
                    .order_by(TextChunk.file_id.asc(), TextChunk.chunk_index.asc())
                )
                result = session.execute(stmt)
                chunks = result.scalars().all()
                logger.info(f"获取到前一天新增的文本块: {len(chunks)} 个")
                return chunks
            except Exception as e:
                logger.error(f"获取前一天文本块失败: {e}")
                return []

    @staticmethod
    def save_qa_batch(qa_list: List[Dict[str, Any]]) -> List[int]:
        """
        批量保存QA记录，qa_list: QA记录列表，每个元素包含question, answer, file_id, chunk_index_list
        返回保存的QA记录ID列表
        """
        if not qa_list:
            return []

        qa_ids = []
        with SessionLocal() as session:
            try:
                for qa_data in qa_list:
                    eval_qa = EvalQA(
                        question=qa_data['question'],
                        answer=qa_data['answer'],
                        file_id=qa_data['file_id'],
                        chunk_index_list=qa_data['chunk_index_list']
                    )
                    session.add(eval_qa)
                    session.flush()
                    qa_ids.append(eval_qa.id)

                session.commit()
                logger.info(f"成功保存 {len(qa_ids)} 条QA记录")
                return qa_ids
            except Exception as e:
                logger.error(f"保存QA记录失败: {e}")
                session.rollback()
                return []

    @staticmethod
    def get_latest_qa_records(limit: int = 500) -> List[EvalQA]:
        """
        获取最新的QA记录。返回QA记录列表，按创建时间倒序
        """
        with SessionLocal() as session:
            try:
                stmt = (
                    select(EvalQA)
                    .order_by(EvalQA.created_at.desc())
                    .limit(limit)
                )
                result = session.execute(stmt)
                records = result.scalars().all()
                return records
            except Exception as e:
                logger.error(f"获取最新QA记录失败: {e}")
                return []

    @staticmethod
    def get_chunks_by_file_id_and_indices(file_id: int, chunk_indices: List[int]) -> List[TextChunk]:
        """
        根据file_id和chunk_index列表获取文本块。file_id: 文件ID, chunk_indices: chunk_index列表
        返回获取到的文本块列表
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
                logger.error(f"根据file_id和chunk_indices查询文本块失败: {e}")
                return []

    @staticmethod
    def get_page_chunks_by_file_and_page(file_id: int, page_index: int) -> List[TextChunk]:
        """
        根据file_id和page_index获取该页面对应的所有chunk。file_id: 文件ID。page_index: 页面索引
        返回chunk_index列表
        """
        with SessionLocal() as session:
            try:
                # 1获取page_id
                page_stmt = (
                    select(TextPage)
                    .where(
                        and_(
                            TextPage.file_id == file_id,
                            TextPage.page_index == page_index
                        )
                    )
                )
                result = session.execute(page_stmt)
                page = result.scalars().first()

                if not page:
                    return []

                # 2获取该页面的所有chunks
                chunk_stmt = (
                    select(TextChunk)
                    .where(TextChunk.page_id == page.id)
                    .order_by(TextChunk.chunk_index.asc())
                )
                result = session.execute(chunk_stmt)
                chunks = result.scalars().all()
                return [chunk.chunk_index for chunk in chunks]
            except Exception as e:
                logger.error(f"根据file_id和page_index查询chunks失败: {e}")
                return []


class EvalResultRepositorySync:
    """
    eval_result表数据库操作类
    """

    @staticmethod
    def save_eval_results(results: List[Dict[str, Any]]) -> List[int]:
        """
        批量保存评测结果。results: 评测结果列表
        返回保存的记录ID列表
        """
        if not results:
            return []

        result_ids = []
        with SessionLocal() as session:
            try:
                for result_data in results:
                    eval_result = EvalResult(
                        qa_id=result_data['qa_id'],
                        chat_answer=result_data['chat_answer'],
                        retrieved_chunks=result_data['retrieved_chunks'],
                        recall_accuracy=result_data['recall_accuracy'],
                        fact_consistency_score=result_data['fact_consistency_score'],
                        completeness_score=result_data['completeness_score'],
                        total_score=result_data['total_score'],
                        batch_id=result_data['batch_id']
                    )
                    session.add(eval_result)
                    session.flush()
                    result_ids.append(eval_result.id)

                session.commit()
                logger.info(f"成功保存 {len(result_ids)} 条评测结果")
                return result_ids
            except Exception as e:
                logger.error(f"保存评测结果失败: {e}")
                session.rollback()
                return []
