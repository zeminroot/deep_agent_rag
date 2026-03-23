#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   database_sync.py
@Author  :   zemin
@Desc    :   SQLAlchemy 操作数据库
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from loguru import logger
from config.config import get_settings


settings = get_settings()

Base = declarative_base()

# 创建同步数据库引擎
# mysql+aiomysql 改为 mysql+pymysql
sync_database_url = settings.database_url.replace("mysql+aiomysql", "mysql+pymysql")

engine = create_engine(
    sync_database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# 创建同步会话工厂 Session 
SessionLocal = sessionmaker(
    engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


def get_db():
    """
    获取数据库会话对象
    """
    session = SessionLocal()
    try:
        yield session
        # 没有异常，提交事务
        session.commit()
    except Exception as e:
        # 发生异常，回滚事务
        logger.error(f"数据库操作失败: {e}")
        session.rollback()
        raise
    finally:
        # 关闭会话
        session.close()


if __name__ == "__main__":
    try:
        session = SessionLocal()
        from sqlalchemy import text
        result = session.execute(text("SELECT 1"))
        print(f"数据库连接成功: {result.scalar()}")
        session.close()
    except Exception as e:
        print(f"数据库连接失败: {e}")
