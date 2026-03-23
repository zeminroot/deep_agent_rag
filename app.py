#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   app.py
@Author  :   zemin
@Desc    :   FastAPI 主应用入口
统一创建FastAPI应用，注入各模块路由，管理后台任务
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger
from pydantic import BaseModel, Field
from typing import Optional
from config.config import get_settings
from main_agent.main_agent import MainAgent
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from knowledge_base.document_task_sync import DocumentProcessTaskSync
from auto_eval.eval_task_sync import RAGEvalTaskSync
from document_upload.api import router as upload_router


# 创建 MainAgent 实例
main_agent = MainAgent()

# 文档切分-embedding-es入库任务实例
document_process_task = DocumentProcessTaskSync(
    chunk_size=1000,
    chunk_overlap=100,
    split_mode="markdown_ast"
)

# 定时自动化评测任务实例
eval_task = RAGEvalTaskSync()

# 使用 BackgroundScheduler开辟一个独立的线程执行后台任务
scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=4)},
    job_defaults={
        "max_instances": 1  # 如果上次任务未结束，本次执行跳过
    },
    daemon=True
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    生命周期管理，启动时在后台开辟两个线程自动启动文档处理定时任务和RAG评测定时任务
    """
    settings = get_settings()
    logger.info("FastAPI应用启动")
    logger.info("启动文档处理定时任务，每分钟0s执行一次")
    scheduler.add_job(
        document_process_task.execute,
        CronTrigger(minute="*", second="0"), 
        id='file_process_job',
        name='文档处理任务'
    )

    # 添加RAG评测定时任务，每天凌晨2点执行
    logger.info("启动RAG评测定时任务，每天凌晨2点执行")
    scheduler.add_job(
        eval_task.execute,
        CronTrigger(hour="2", minute="0"),  
        # CronTrigger(minute="*/5", second="0"),  # 测试每5分钟的第0秒执行
        id='rag_eval_job',
        name='RAG评测任务'
    )

    scheduler.start()

    logger.info("文档处理定时任务已启动")
    logger.info("RAG评测定时任务已启动")

    yield

    logger.info("FastAPI应用关闭")
    scheduler.shutdown()
    logger.info("所有定时任务已停止")


app = FastAPI(
    title="RAG系统API",
    version="1.0.0",
    lifespan=lifespan
)


class ChatRequest(BaseModel):
    """
    对话接口请求
    """
    query: str = Field(..., description="用户发言")
    user_id: str = Field(default="default_user", description="用户ID")
    session_id: str = Field(default="default_session", description="多轮对话session_id")
    request_id: Optional[str] = Field(default=None, description="单词请求ID")


class ChatResponse(BaseModel):
    """
    对话接口响应
    """
    request_id: str = Field(..., description="单词请求id")
    answer: str = Field(..., description="Agent回答结果")
    retrieved_chunks: list = Field(default=[], description="参考的文档片段信息")


@app.post("/chat", response_model=ChatResponse, tags=["对话"])
async def chat(request: ChatRequest):
    """
    对话接口，调用main_agent处理问题
    """
    try:
        result = await main_agent.process_single_query(
            user_id=request.user_id,
            session_id=request.session_id,
            query=request.query,
            request_id=request.request_id
        )
        return ChatResponse(
            request_id=result["request_id"],
            answer=result["answer"],
            retrieved_chunks=result.get("retrieved_chunks", [])
        )
    except Exception as e:
        logger.error(f"chat接口调用失败: {e}")
        raise


# 注入各模块路由
app.include_router(upload_router)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "app:app",
        host=settings.app_host,
        port=settings.app_port,
        workers=1,
        reload=False
    )