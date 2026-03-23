#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   redis_client.py
@Author  :   zemin
@Desc    :   Redis 客户端工具模块，提供全局异步 Redis 客户端单例
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from typing import Optional
from redis.asyncio import Redis as AsyncRedis
from loguru import logger
from config.config import get_settings


# 全局 Redis 客户端实例
_redis_client: Optional[AsyncRedis] = None
# 初始化锁
_redis_lock = asyncio.Lock()


async def get_redis_client() -> AsyncRedis:
    """
    获取 Redis 客户端单例
    使用双重检查锁定模式防止并发创建多个连接

    Returns:
        AsyncRedis: 异步 Redis 客户端实例
    """
    global _redis_client
    if _redis_client is None:
        async with _redis_lock:
            if _redis_client is None:
                settings = get_settings()
                _redis_client = AsyncRedis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    password=settings.redis_password,
                    decode_responses=True
                )
                logger.debug("Redis 客户端初始化完成")
    return _redis_client


async def close_redis_client():
    """
    关闭 Redis 客户端连接
    应在应用关闭时调用
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis 客户端连接已关闭")


async def save_retrieval_record(
    request_id: str,
    tool_name: str,
    records: list,
    tool_args: dict = None
) -> bool:
    """
    保存检索记录到 Redis

    Args:
        request_id: 请求 ID
        tool_name: 工具名称
        records: 检索记录列表，如 [{"file_id": 123, "chunk_index": 5}, ...]
        tool_args: 工具调用参数

    Returns:
        是否保存成功
    """
    from datetime import datetime
    import uuid
    import json

    if not request_id or not records:
        return False

    try:
        redis_client = await get_redis_client()
        settings = get_settings()

        call_id = f"{tool_name}_{uuid.uuid4().hex[:8]}"
        retrieval_key = f"retrieval:{request_id}"

        metadata = {
            "tool_name": tool_name,
            "timestamp": datetime.now().isoformat(),
            "tool_args": tool_args or {},
            "records": records
        }

        await redis_client.hset(
            retrieval_key,
            call_id,
            json.dumps(metadata, ensure_ascii=False)
        )
        await redis_client.expire(retrieval_key, settings.redis_state_ttl)

        logger.info(f"保存检索记录: request_id={request_id}, tool={tool_name}, records={len(records)}")
        return True
    except Exception as e:
        logger.error(f"保存检索记录失败: {e}")
        return False
