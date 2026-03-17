#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   redis_lock.py
@Author  :   zemin
@Desc    :   redis分布式锁
'''


import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Optional
from loguru import logger
from redis.asyncio import Redis as AsyncRedis
from config.config import get_settings


class RedisLock:
    """
    Redis分布式锁工具类
    使用Redis实现分布式锁，防止多个服务实例同时处理相同数据
    """

    def __init__(
        self,
        lock_timeout: int = 10,
        lock_prefix: str = "doc_process:"
    ):
        """
        初始化Redis锁工具

        Args:
            lock_timeout: 锁超时时间（秒），默认10s
            lock_prefix: 锁的键前缀，默认"doc_process:"
        """
        settings = get_settings()

        self.redis_client = AsyncRedis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True
        )
        self.lock_timeout = lock_timeout
        self.lock_prefix = lock_prefix

        logger.info("Redis分布式锁工具初始化完成")

    async def acquire(self, lock_key: str) -> bool:
        """
        获取锁

        Args:
            lock_key: 锁的键名

        Returns:
            是否获取成功
        """
        full_key = f"{self.lock_prefix}{lock_key}"

        try:
            # NX: 只在键不存在时设置
            result = await self.redis_client.set(
                full_key,
                "1",  # 锁值
                ex=self.lock_timeout,  
                nx=True  # 只在不存在时设置
            )
            if result:
                logger.info(f"获取锁成功: {full_key}")
            else:
                logger.warning(f"获取锁失败（锁已存在）: {full_key}")
            return result
        except Exception as e:
            logger.error(f"获取锁失败: {e}")
            return False
        

    async def release(self, lock_key: str):
        """
        释放锁

        Args:
            lock_key: 锁的键名
        """
        full_key = f"{self.lock_prefix}{lock_key}"

        try:
            await self.redis_client.delete(full_key)
            logger.info(f"释放锁成功: {full_key}")
        except Exception as e:
            logger.error(f"释放锁失败: {e}")
            

    async def is_locked(self, lock_key: str) -> bool:
        """
        检查锁是否存在

        Args:
            lock_key: 锁的键名

        Returns:
            锁是否存在
        """
        full_key = f"{self.lock_prefix}{lock_key}"

        try:
            return await self.redis_client.exists(full_key) > 0
        except Exception as e:
            logger.error(f"检查锁失败: {e}")
            return False


if __name__ == "__main__":
    import asyncio

    async def test():
        lock = RedisLock()

        acquired = await lock.acquire("test_lock")
        print(f"获取锁结果: {acquired}")

        if acquired:
            is_locked = await lock.is_locked("test_lock")
            print(f"锁是否存在: {is_locked}")

            # # 释放锁
            # await lock.release("test_lock")

            acquired3 = await lock.acquire("test_lock")
            print(f"释放后获取锁结果: {acquired3}")

            # 关闭 Redis 连接
            await lock.redis_client.aclose()

    asyncio.run(test())
