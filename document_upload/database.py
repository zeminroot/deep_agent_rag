#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   database.py
@Author  :   zemin
@Desc    :
SQLAlchemy 操作数据库
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from loguru import logger
from config.config import get_settings


settings = get_settings()

# 创建基类，所有 ORM 模型都继承自此
Base = declarative_base()

# 创建异步数据库引擎
engine = create_async_engine(
    settings.database_url,
    echo=False,  # 是否打印 SQL 语句
    pool_size=10,  # 连接池大小
    max_overflow=20,  # 连接池最大溢出连接数
    pool_pre_ping=True,  # 检查连接是否有效
    pool_recycle=3600,  # 连接回收时间（秒）
)

# 创建异步会话工厂 Session 用于执行数据库操作
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # 提交后不过期对象，方便访问
    autocommit=False,  # 不自动提交
    autoflush=False,  # 不自动刷新
)


async def get_db():
    """
    获取数据库会话对象（依赖注入）
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # 没有异常，提交事务
            await session.commit()
        except Exception as e:
            # 发生异常，回滚事务
            logger.error(f"数据库操作失败: {e}")
            await session.rollback()
            raise
        finally:
            # 关闭会话
            await session.close()


if __name__ == "__main__":
    import asyncio

    async def test_connection():
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import text
                result = await session.execute(text("SELECT 1"))
                print(f"数据库连接成功: {result.scalar()}")
        except Exception as e:
            print(f"数据库连接失败: {e}")

    # 测试
    asyncio.run(test_connection())
