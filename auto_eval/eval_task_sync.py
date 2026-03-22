#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   eval_task_sync.py
@Author  :   zemin
@Desc    :   RAG自动评测任务（同步版本）
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict
from loguru import logger
from openai import OpenAI
import requests
import traceback
import time
from config.config import get_settings
from auto_eval.database_sync import EvalQARepositorySync, EvalResultRepositorySync
from auto_eval.models import EvalQA
from utils.prompt_loader import load_prompt
from utils.redis_lock import RedisLock


class RAGEvalTaskSync:
    """
    RAG自动评测任务类
    """

    def __init__(self):
        self.settings = get_settings()
        self.openai_client = OpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
        )
        self.model = self.settings.llm_model
        self.chunk_group_size = 60  # 每60个文本块为一组
        self.questions_per_group = 6  # 每组生成6个问题
        self.redis_lock = RedisLock()

    def _group_chunks_by_file(self, chunks: List[Any]) -> Dict[int, List[Any]]:
        """
        按file_id对文本块进行分组。chunks: 文本块列表
        返回按file_id分组的字典
        """
        grouped = defaultdict(list)
        for chunk in chunks:
            grouped[chunk.file_id].append(chunk)
        return grouped

    def _create_chunk_groups(self, chunks: List[Any]) -> List[List[Any]]:
        """
        将文本块按chunk_index排序后，每60个分为一组。chunks: 文本块列表
        返回分组后的文本块列表
        """
        sorted_chunks = sorted(chunks, key=lambda x: x.chunk_index)

        groups = []
        for i in range(0, len(sorted_chunks), self.chunk_group_size):
            group = sorted_chunks[i:i + self.chunk_group_size]
            groups.append(group)

        return groups

    def _generate_questions(self, chunks: List[Any], file_id: int) -> List[Dict[str, Any]]:
        """
        根据文本块内容生成问题和答案。chunks: 文本块列表。file_id: 文件ID
        返回生成的QA列表，每个元素包含question, answer, chunk_index_list
        """
        chunk_contents = []
        chunk_indices = []
        for chunk in chunks:
            chunk_contents.append(f"[Chunk {chunk.chunk_index}]\n{chunk.chunk_content}")
            chunk_indices.append(chunk.chunk_index)

        context = "\n\n".join(chunk_contents)

        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "generate_questions.md")
        prompt = load_prompt(
            prompt_path,
            questions_per_group=self.questions_per_group,
            context=context
        )

        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的问答对生成助手，擅长根据文本内容生成高质量的问答对。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4096
            )

            content = response.choices[0].message.content.strip()

            # 清理可能的markdown代码块
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            qa_list = json.loads(content)

            # 添加file_id到每个QA记录
            for qa in qa_list:
                qa['file_id'] = file_id

            logger.info(f"成功生成 {len(qa_list)} 个问答对，file_id={file_id}")
            return qa_list

        except Exception as e:
            logger.error(f"生成问答对失败，file_id={file_id}: {e}")
            return []

    def _call_chat_api(self, question: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        调用本地chat接口获取答案和检索的chunks。question: 问题。max_retries: 最大重试次数
        返回包含answer和retrieved_chunks的字典
        """
        base_url = f"http://127.0.0.1:{self.settings.app_port}/chat"

        payload = {
            "query": question,
            "user_id": "eval_user",
            "session_id": f"eval_session_{uuid.uuid4().hex[:8]}",
            "request_id": None
        }

        for attempt in range(max_retries):
            try:
                logger.info(f"调用chat接口, 问题: {question}\n(尝试 {attempt + 1}/{max_retries})")

                response = requests.post(
                    base_url,
                    json=payload,
                    timeout=1200.0  
                )
                response.raise_for_status()
                result = response.json()

                logger.info(f"chat接口调用成功")
                return {
                    "answer": result.get("answer", ""),
                    "retrieved_chunks": result.get("retrieved_chunks", [])
                }

            except requests.exceptions.Timeout as e:
                logger.error(f"调用chat接口超时 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"chat接口调用失败，已达到最大重试次数")
                    return {
                        "answer": "",
                        "retrieved_chunks": []
                    }
                time.sleep(2)  

            except Exception as e:
                logger.error(f"调用chat接口失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return {
                        "answer": "",
                        "retrieved_chunks": []
                    }
                time.sleep(2)
                
        return {
            "answer": "",
            "retrieved_chunks": []
        }

    def _convert_page_index_to_chunk_indices(
        self,
        retrieved_chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        将retrieved_chunks中的page_index转换为chunk_index
        retrieved_chunks: 检索到的chunks列表
        返回转换后的chunks列表
        """
        converted = []

        for chunk in retrieved_chunks:
            file_id = chunk.get("file_id")

            if "chunk_index" in chunk:
                converted.append(chunk)
            elif "page_index" in chunk:
                # 转换为chunk_index
                page_index = chunk.get("page_index")
                chunk_indices = EvalQARepositorySync.get_page_chunks_by_file_and_page(
                    file_id=file_id,
                    page_index=page_index
                )

                for ci in chunk_indices:
                    converted_chunk = chunk.copy()
                    converted_chunk["chunk_index"] = ci
                    converted.append(converted_chunk)
            else:
                converted.append(chunk)

        return converted

    def _calculate_recall_accuracy(
        self,
        retrieved_chunks: List[Dict[str, Any]],
        expected_chunks: List[int]
    ) -> int:
        """
        计算召回准确率。
        retrieved_chunks: 实际召回的chunks
        expected_chunks: 期望召回的chunk_index列表
        返回召回准确率(0-100)
        """
        if not expected_chunks:
            return 0

        # 获取实际召回的chunk_index集合
        retrieved_indices = set()
        for chunk in retrieved_chunks:
            if "chunk_index" in chunk:
                retrieved_indices.add(chunk["chunk_index"])

        # 计算召回率
        expected_set = set(expected_chunks)
        if not expected_set:
            return 0

        hit_count = len(retrieved_indices & expected_set)
        accuracy = int((hit_count / len(expected_set)) * 100)

        return accuracy

    def _evaluate_answer_quality(
        self,
        question: str,
        expected_answer: str,
        chat_answer: str
    ) -> Dict[str, int]:
        """
        评测答案质量
        question: 问题
        expected_answer: 期望答案
        chat_answer: chat接口返回的答案
        返回包含fact_consistency_score和completeness_score的字典
        """
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "evaluate_answer_quality.md")
        prompt = load_prompt(
            prompt_path,
            question=question,
            expected_answer=expected_answer,
            chat_answer=chat_answer
        )

        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的答案质量评测助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=512
            )

            content = response.choices[0].message.content.strip()

            # 清理可能的markdown代码块
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            result = json.loads(content)

            return {
                "fact_consistency_score": result.get("fact_consistency_score", 0),
                "completeness_score": result.get("completeness_score", 0)
            }

        except Exception as e:
            logger.error(f"评测答案质量失败: {e}")
            return {
                "fact_consistency_score": 0,
                "completeness_score": 0
            }

    def execute(self):
        """
        执行评测任务的主流程
        使用Redis分布式锁防止多实例重复执行
        """
        lock_key = "rag_eval_task"

        # 尝试获取锁
        acquired = self.redis_lock.acquire(lock_key)
        if not acquired:
            logger.info("其他实例正在执行评测任务，跳过本次执行")
            return
        else:
            logger.info("获取Redis锁成功，开始执行评测任务")

        try:
            self._execute_eval_task()
        finally:
            # 释放Redis锁
            self.redis_lock.release(lock_key)

    def _execute_eval_task(self):
        """
        执行评测任务的核心逻辑
        """
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"开始RAG评测任务，批次ID: {batch_id}")

        try:
            # 1、获取前一天新增的文本块
            logger.info("步骤1: 获取前一天新增的文本块")
            chunks = EvalQARepositorySync.get_yesterday_chunks()
            if not chunks:
                logger.info("前一天没有新增文本块，任务结束")
                return

            # 2、按file_id分组
            logger.info("步骤2: 按file_id分组文本块")
            grouped_chunks = self._group_chunks_by_file(chunks)
            logger.info(f"共有 {len(grouped_chunks)} 个文件需要处理")

            # 3、对每个file_id的文本块分组生成QA
            logger.info("步骤3: 生成QA记录")
            all_qa_records = []

            for file_id, file_chunks in list(grouped_chunks.items())[:20]:
                chunk_groups = self._create_chunk_groups(file_chunks)
                logger.info(f"文件 {file_id} 分为 {len(chunk_groups)} 组")
                for group in chunk_groups[:]:
                    qa_list = self._generate_questions(group, file_id)
                    all_qa_records.extend(qa_list)

            if not all_qa_records:
                logger.warning("没有生成任何QA记录，任务结束")
                return

            # 4、保存QA记录到数据库
            logger.info(f"步骤4: 保存 {len(all_qa_records)} 条QA记录到数据库")
            qa_ids = EvalQARepositorySync.save_qa_batch(all_qa_records)

            if not qa_ids:
                logger.error("保存QA记录失败，任务结束")
                return

            # 5、拉取最新的500条QA记录作为测试集
            logger.info("步骤5: 拉取最新500条QA记录作为测试集")
            test_records = EvalQARepositorySync.get_latest_qa_records(limit=500)

            if not test_records:
                logger.warning("没有可用的测试记录，任务结束")
                return

            # 6、对每个问题进行评测
            logger.info(f"步骤6: 对 {len(test_records)} 条记录进行评测")
            eval_results = []

            for record in test_records[:]:
                # 调用chat接口
                chat_result = self._call_chat_api(record.question)
                logger.info(f"record.question:{record.question}\nrecord.answer:{record.answer}\nchat_result:{chat_result}")

                # 转换page_index为chunk_index
                retrieved_chunks = self._convert_page_index_to_chunk_indices(
                    chat_result["retrieved_chunks"]
                )

                # 计算召回率
                recall_accuracy = self._calculate_recall_accuracy(
                    retrieved_chunks,
                    record.chunk_index_list
                )

                # 评测答案质量
                quality_scores = self._evaluate_answer_quality(
                    record.question,
                    record.answer,
                    chat_result["answer"]
                )

                # 计算总得分
                total_score = (
                    quality_scores["fact_consistency_score"] +
                    quality_scores["completeness_score"]
                )

                eval_results.append({
                    "qa_id": record.id,
                    "chat_answer": chat_result["answer"],
                    "retrieved_chunks": retrieved_chunks,
                    "recall_accuracy": recall_accuracy,
                    "fact_consistency_score": quality_scores["fact_consistency_score"],
                    "completeness_score": quality_scores["completeness_score"],
                    "total_score": total_score,
                    "batch_id": batch_id
                })

            # 7、保存评测结果
            logger.info("步骤7: 保存评测结果")
            EvalResultRepositorySync.save_eval_results(eval_results)

            if eval_results:
                logger.info(f"RAG评测任务完成！")
                logger.info(f"评测记录数: {len(eval_results)}")

        except Exception as e:
            logger.error(f"RAG评测任务执行失败: {e}")
            raise



if __name__ == "__main__":
    task = RAGEvalTaskSync()
    task.execute()
