# -*- coding: utf-8 -*-
"""
Cookie 工具函数
基于 jiji262/douyin-downloader utils/cookie_utils.py
"""

import re
from typing import Dict, Optional


def sanitize_cookies(cookies: Optional[Dict[str, str]]) -> Dict[str, str]:
    """清理和标准化 Cookie 字典"""
    if not cookies:
        return {}
    result: Dict[str, str] = {}
    for key, value in cookies.items():
        if not key or not value:
            continue
        key = str(key).strip()
        value = str(value).strip()
        if key and value:
            result[key] = value
    return result


def parse_cookie_header(cookie_header: Optional[str]) -> Dict[str, str]:
    """从 Cookie header 字符串解析为字典"""
    if not cookie_header:
        return {}
    cookies: Dict[str, str] = {}
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part:
            continue
        # 支持 key=value 和 key="value" 格式
        match = re.match(r'^([^=]+)=(.*)$', part)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            # 移除引号
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            if key and value:
                cookies[key] = value
    return cookies