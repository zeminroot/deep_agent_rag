#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   tool_manager.py
@Author  :   zemin
@Desc    :   
适配openai格式的工具装饰器
工具管理器，自动扫描模块，实现工具自动注册
'''

import inspect
import json
from loguru import logger


# OpenAI工具格式的装饰器
def tool(name: str, description: str, properties: dict, required: list = None):
    required = required or []
    def decorator(func):
        func._tool_name = name
        func._openai_tool = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
        return func
    return decorator


# 工具管理器
class ToolManager:
    def __init__(self):
        self.tool_registry = {}

    def register(self, func):
        tool_info = func._openai_tool
        tool_name = tool_info["function"]["name"]
        self.tool_registry[tool_name] = {"func": func, "openai_tool": tool_info}
        logger.info(f"注册工具成功: {tool_name}")

    def register_from_module(self, module):
        logger.info(f"扫描模块: {module.__name__}")
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and hasattr(obj, '_openai_tool'):
                self.register(obj)

    async def get_openai_tools(self):
        return [t["openai_tool"] for t in self.tool_registry.values()]

    
    async def execute_tool(self, tool_name: str, tool_args: dict):
        """
        tool_name: 工具名称
        tool_args: 工具参数
        返回工具执行结果
        """
        tool = self.tool_registry.get(tool_name)
        if not tool: 
            return f"工具{tool_name}不存在"
        
        func = tool["func"]
        try:
            if inspect.iscoroutinefunction(func):
                # 异步工具
                logger.info(f"执行【异步工具】: {tool_name}, 参数: {tool_args}")
                result = await func(**tool_args)
            else:
                # 同步工具
                logger.info(f"执行【同步工具】: {tool_name}, 参数: {tool_args}")
                result = func(**tool_args)
            
            return result if result is not None else "工具执行成功，无返回结果"
        
        except Exception as e:
            error_msg = f"工具【{tool_name}】执行失败。"
            logger.error(f"工具【{tool_name}】执行失败: {e}")
            return error_msg