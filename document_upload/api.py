#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   api.py
@Author  :   zemin
@Desc    :   文件上传API路由, 调用路由接口，将文件上传到OSS并记录到MySQL
'''

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tempfile
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
from pydantic import BaseModel
from document_upload.database import get_db
from document_upload.models import FileRecord
from document_upload.oss_service import get_oss_service, OSSService


# 创建路由器
router = APIRouter(prefix="/upload", tags=["文件上传"])


class UploadResponse(BaseModel):
    """
    文件上传成功响应
    """
    code: int
    message: str
    data: dict


@router.post("/file", response_model=UploadResponse, summary="上传文件")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    oss_service: OSSService = Depends(get_oss_service)
):
    """
    文件上传接口
    1. 接收用户上传的文件和用户ID
    2. 将文件上传到阿里云OSS
    3. 将文件URL保存到MySQL数据库
    """
    try:
        filename = file.filename
        if not filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        logger.info(f"用户 {user_id} 开始上传文件: {filename}")

        # 保存到临时文件
        temp_file_path = os.path.join(tempfile.gettempdir(), filename)
        with open(temp_file_path, "wb") as temp_file:
            content = await file.read()
            temp_file.write(content)

        # 上传到OSS
        try:
            oss_url = oss_service.upload_file(
                file_path=temp_file_path,
                filename=filename,
                prefix=f"uploads/{user_id}"
            )
            logger.info(f"文件已上传到OSS: {oss_url}")
        finally:
            # 删除临时文件
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

        # 保存到mysql
        file_record = FileRecord(user_id=user_id, file_url=oss_url, is_read=False)
        db.add(file_record)
        await db.commit()
        await db.refresh(file_record)

        logger.info(f"文件记录已保存，ID: {file_record.id}")

        return UploadResponse(
            code=200,
            message="文件上传成功",
            data={
                "file_id": file_record.id,
                "user_id": file_record.user_id,
                "file_url": file_record.file_url,
                "is_read": file_record.is_read,
                "created_at": file_record.created_at.isoformat() if file_record.created_at else None
            }
        )
        
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        db.rollback()
        return UploadResponse(
            code=500,
            message=f"文件上传失败: {str(e)}",
            data={}
        )
        

@router.get("/files", response_model=UploadResponse, summary="查询用户文件")
async def get_user_files(
    user_id: str,
    is_read: bool = None,
    db: AsyncSession = Depends(get_db)
):
    """
    根据user_id查询用户上传的的文件列表
    """
    try:
        query = select(FileRecord).where(FileRecord.user_id == user_id)
        if is_read is not None:
            query = query.where(FileRecord.is_read == is_read)
        query = query.order_by(FileRecord.created_at.desc())

        result = await db.execute(query)
        files = result.scalars().all()

        return UploadResponse(
            code=200,
            message=f"查询成功，共{len(files)}条数据",
            data={"files": [f.to_dict() for f in files], "total": len(files)}
        )

    except Exception as e:
        logger.error(f"查询文件失败: {e}")  
        db.rollback()
      
        return UploadResponse(
            code=500,
            message=f"文件查询失败: {str(e)}",
            data={}
        )


@router.put("/files/{file_id}/read", response_model=UploadResponse, summary="标记文件已读")
async def mark_file_as_read(
    file_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    标记文件为已读状态
    """
    try:
        query = select(FileRecord).where(FileRecord.id == file_id)
        result = await db.execute(query)
        file_record = result.scalar_one_or_none()

        file_record.is_read = True
        await db.commit()
        await db.refresh(file_record)

        logger.info(f"文件 {file_id} 已标记为已读")

        return UploadResponse(
            code=200,
            message="标记成功",
            data=file_record.to_dict()
        )
    except Exception as e:
        logger.error(f"标记失败: {e}")
        db.rollback()
        return UploadResponse(
            code=500,
            message=f"标记失败: {str(e)}",
            data={}
        )