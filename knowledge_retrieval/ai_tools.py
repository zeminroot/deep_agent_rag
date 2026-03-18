#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   ai_tools.py
@Author  :   zemin
@Desc    :   Agent用到的工具
'''
from tool_manager import tool


class WeatherService:
    """
    天气服务类
    """
    def __init__(self):
        print("创建天气服务实例……")
    
    def get_real_weather(self, city: str) -> str:
        return f"今天天气多云9度，微风"


class CalcService:
    """
    计算服务类
    """
    def calc(self, a: float, b: float, op: str) -> float | str:
        if op == "+": return a + b
        if op == "-": return a - b
        if op == "*": return a * b
        return "不支持的运算"


weather_client = WeatherService()
calc_client = CalcService()

@tool(
    name="get_weather",
    description="查询城市天气",
    properties={"city": {"type": "string", "description": "城市名"}},
    required=["city"]
)
async def get_weather(city: str):
    return weather_client.get_real_weather(city)


@tool(
    name="calculate",
    description="数字计算",
    properties={
        "a": {"type": "number"},
        "b": {"type": "number"},
        "op": {"type": "string", "description": "运算符 + - * /"}
    },
    required=["a", "b", "op"]
)
async def calculate(a: float, b: float, op: str):
    return calc_client.calc(a, b, op)

