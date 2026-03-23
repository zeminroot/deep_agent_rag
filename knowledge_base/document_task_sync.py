#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   document_task_sync.py
@Author  :   zemin
@Desc    :   文档处理类，后台任务，单独开辟后台线程
1、使用redis分布式锁防止多实例重复处理数据
2、从mysql获取未读文件：下载、解析、按page页面逐个切分、保存页面page和chunk到mysql、chunk向量化保存到ES
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Optional, List, Dict, Any
from loguru import logger
from config.config import get_settings
from document_analyse.document_parser import DocumentParser, DocumentParseResult
from document_analyse.paddle_ocr_vl_parser import ParseResult
from document_upload.models import FileRecord
from knowledge_base.file_downloader import FileDownloader
from knowledge_base.text_chunker import DocumentTextChunker
from knowledge_base.embedding_model import EmbeddingModel
from knowledge_base.database_sync import FileRecordRepositorySync, TextPageRepositorySync, TextChunkRepositorySync, ChunkPageRepositorySync
from knowledge_base.es_vector_store import ESVectorStore
from utils.redis_lock import RedisLock
from knowledge_base.models import TextPage, TextChunk


class DocumentProcessTaskSync:
    """
    文档处理任务类
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        split_mode: str = "markdown_ast"
    ):
        """
        初始化任务类
        chunk_size: 文本块大小
        chunk_overlap: 文本块重叠大小
        split_mode: 分块模式
        """
        self.settings = get_settings()
        self.file_downloader = FileDownloader()
        self.document_parser = DocumentParser(
            vl_rec_server_url=self.settings.vl_rec_server_url,
            vl_rec_max_concurrency=self.settings.vl_rec_max_concurrency,
            use_layout_detection=self.settings.use_layout_detection,
            use_doc_orientation_classify=self.settings.use_doc_orientation_classify,
            use_doc_unwarping=self.settings.use_doc_unwarping,
            use_chart_recognition=self.settings.use_chart_recognition,
            format_block_content=self.settings.format_block_content
        )
        self.text_chunker = DocumentTextChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        self.split_mode = split_mode
        self.redis_lock = RedisLock(lock_prefix="doc_process:")

        self.embedding_model = EmbeddingModel()
        self.es_store = ESVectorStore(
            hosts=f"http://{self.settings.es_host}:{self.settings.es_port}",
            es_user=self.settings.es_user,
            es_password=self.settings.es_password,
            index_name=self.settings.es_index_knowledge,
            vector_dim=1024,
            similarity="cosine",
        )

        logger.info(f"文档处理任务类初始化完成: split_mode={split_mode}")


    def _save_chunks_to_es(self, all_chunks_data: List[Dict[str, Any]]):
        """
        保存所有文本块到ES
        存储字段：text_chunk mysql表字段 + file_id + file_url + file_total_pages + embedding字段
        """
        texts = [chunk["chunk_content"] for chunk in all_chunks_data]

        # 文本向量化
        vectors = self.embedding_model.encode(texts)

        # 构建ES文档
        es_documents = []
        for chunk_data, vector in zip(all_chunks_data, vectors):
            es_documents.append({
                "_id": f"chunk_{chunk_data['chunk_id']}",
                "id": chunk_data["chunk_id"],
                "chunk_content": chunk_data["chunk_content"],
                "chunk_index": chunk_data["chunk_index"],
                "page_id": chunk_data["page_id"],
                "page_index": chunk_data["page_index"],
                "file_id": chunk_data["file_id"],
                "file_url": chunk_data["file_url"],
                "file_total_pages": chunk_data["file_total_pages"],
                "created_at": chunk_data["created_at"],
                "updated_at": chunk_data["updated_at"],
                "embedding": vector
            })

        # ES批量入库
        success, failed = self.es_store.bulk_index(es_documents, chunk_size=100)
        logger.info(f"ES向量入库完成。成功{success}条。失败{failed}条。")

    def _process_single_page(self, page: ParseResult, file_record: FileRecord, file_total_pages:int, file_chunks_num:int) -> Optional[Dict[str, Any]]:
        """
        处理单个页面
        page: 单个页面 ParseResult: page_index: int; text: str
        file_record: 文件记录
        file_chunks_num: 当前该文件已有的chunk个数
        返回包含该页面下所有chunk数据的字典列表，失败返回None
        """
        try:
            page_text = page.text
            page_index = page.page_index

            # 1切分单个页面
            chunks = self.text_chunker.split_pages(pages=[page], split_mode=self.split_mode, file_chunks_num=file_chunks_num)

            if not chunks:
                logger.warning(f"页面 {page_index} 分块结果为空")
                return None

            logger.info(f"页面 {page_index} 分块成功，共 {len(chunks)} 个chunk")

            # 2保存当前页面到text_page表，获取page_id
            page_id = TextPageRepositorySync.save_pages(
                file_id=file_record.id,
                file_url=file_record.file_url,
                file_total_pages=file_total_pages,
                pages=[{"text": page_text, "page_index": page_index}]
            )

            if not page_id or len(page_id) == 0:
                logger.error(f"保存页面 {page_index} 到MySQL失败")
                return None

            page_id = page_id[0]
            logger.info(f"页面 {page_index} 保存成功，page_id={page_id}")

            # 3保存该页面下的所有chunk到text_chunk表
            chunk_ids = TextChunkRepositorySync.save_chunks_for_page(
                page_id=page_id,
                file_id=file_record.id,
                page_index=page_index,
                chunks=chunks
            )

            if not chunk_ids:
                logger.error(f"保存页面 {page_index} 的chunks到MySQL失败")
                return None

            logger.info(f"页面 {page_index} 的 {len(chunk_ids)} 个chunk保存成功")

            # 4获取保存的chunk记录详细信息，返回用于后续ES存储和chunk_page关联表
            all_chunks_data = []
            chunk_page_relations = []
            for idx, chunk_id in enumerate(chunk_ids):
                chunk_record = TextChunkRepositorySync.get_chunk_by_id(chunk_id)
                if chunk_record:
                    all_chunks_data.append({
                        "chunk_id": chunk_record.id,
                        "chunk_content": chunk_record.chunk_content,
                        "chunk_index": chunk_record.chunk_index,
                        "page_id": chunk_record.page_id,
                        "page_index": page_index,
                        "file_id": file_record.id,
                        "file_url": file_record.file_url,
                        "file_total_pages": file_total_pages,
                        "created_at": chunk_record.created_at.isoformat() if chunk_record.created_at else None,
                        "updated_at": chunk_record.updated_at.isoformat() if chunk_record.updated_at else None,
                    })
                    # 准备chunk_page关联关系数据
                    chunk_page_relations.append({
                        "chunk_id": chunk_record.id,
                        "chunk_index": chunk_record.chunk_index,
                        "page_id": page_id,
                        "page_index": page_index
                    })
                else:
                    continue

            # 5保存chunk_page关联关系到数据库
            if chunk_page_relations:
                chunk_page_ids = ChunkPageRepositorySync.save_chunk_page_relations(
                    file_id=file_record.id,
                    file_url=file_record.file_url,
                    chunk_page_relations=chunk_page_relations
                )
                logger.info(f"页面 {page_index} 的 {len(chunk_page_ids)} 个chunk_page关联记录保存成功")

            return all_chunks_data

        except Exception as e:
            logger.error(f"处理页面 {page.page_index} 时发生错误: {e}")
            return None

    def process_file(self, file_record):
        """
        处理单个文件
        """
        logger.info(f"开始处理文件: {file_record.id}")

        local_path = None
        try:
            # 从oss下载文件
            local_path = self.file_downloader.download_file(file_record.file_url)
            if not local_path:
                logger.error(f"文件下载失败: {file_record.file_url}")
                return False
            logger.info(f"文件下载成功, 下载地址: {local_path}")

            # 解析文件
            parse_result = self.document_parser.parse(local_path, output_format="markdown")
            if not parse_result.success:
                logger.error(f"文件解析失败")
                return False
            else:
                logger.info(f"文件解析成功, 共 {parse_result.total_pages} 页")

            # 按页面逐个处理
            all_chunks_data = []
            for page in parse_result.pages:
                try:
                    chunks_data = self._process_single_page(page=page, file_record=file_record, file_total_pages=parse_result.total_pages, file_chunks_num=len(all_chunks_data))
                    if chunks_data:
                        all_chunks_data.extend(chunks_data)
                    else:
                        logger.warning(f"页面 {page.page_index} 处理失败，跳过")
                        continue
                except Exception as e:
                    logger.error(f"{e}\n本页处理异常，跳过本页，继续处理剩余页面。")
                    continue

            logger.info(f"文件 {file_record.id} 处理完成。共 {len(all_chunks_data)} 个chunk")

            # 保存所有chunk到ES
            if all_chunks_data:
                logger.info("\n开始存入es")
                self._save_chunks_to_es(all_chunks_data)

            return True

        except Exception as e:
            logger.error(f"处理文件时发生错误: {e}")
            return False

        finally:
            # 文件处理完，清除临时文件
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                    logger.info(f"临时文件已删除: {local_path}")
                except Exception as e:
                    logger.warning(f"删除临时文件失败: {e}")


    def _mark_files_as_processing(self, file_ids: list) -> bool:
        """
        标记文件为处理中（is_read=true），防止其他实例重复处理
        file_ids: 文件ID列表
        返回是否标记成功
        """
        return FileRecordRepositorySync.mark_files_as_processing(file_ids)

    def execute(self, limit: int = 1000):
        """
        处理mysql中未被读取的文件
        1、获取Redis分布式锁
        2、读取MySQL中isread=false的文件
        3、先将isread置为true，防止其他实例重复读取
        4、释放锁后调用函数进入文件处理逻辑（包括：切分、存mysql、转embedding、存es）
        """

        # Redis锁的键名
        lock_key = "file_processing"

        # 尝试获取锁
        acquired = self.redis_lock.acquire(lock_key)
        if not acquired:
            logger.info("其他实例正在处理文件，跳过本次执行")
            return
        else:
            logger.info("获取redis锁成功，开始执行任务")

        files = []
        try:
            # 1、读取MySQL中isread=false的文件
            files = FileRecordRepositorySync.get_unread_files(limit=limit)
            logger.info(f"从mysql找到 {len(files)} 个未读的文件:\n{files}")

            if not files:
                return

            # 2、先将isread置为true，防止其他实例重复读取
            file_ids = [f.id for f in files]
            mark_res = self._mark_files_as_processing(file_ids)
            if not mark_res:
                logger.error("标记文件为处理中失败，跳过本次执行")
                return
            else:
                logger.info(f"已标记 {len(files)} 个文件为已读，开始处理处理这些文件……")
        finally:
            # 3、释放Redis锁，让其他实例可以处理新文件
            self.redis_lock.release(lock_key)

        # 4、锁释放后，进行文件处理逻辑
        for file_record in files:
            self.process_file(file_record)


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("开始测试 DocumentProcessTaskSync")
    logger.info("=" * 60)

    task = DocumentProcessTaskSync(
        chunk_size=1000,
        chunk_overlap=100,
        split_mode="markdown_ast"
    )

    task.execute(limit=1000)

    logger.info("=" * 60)
    logger.info("DocumentProcessTaskSync 测试完成")
    logger.info("=" * 60)
