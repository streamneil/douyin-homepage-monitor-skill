# -*- coding: utf-8 -*-
"""
msToken 管理器
基于 jiji262/douyin-downloader auth/ms_token_manager.py
参考 F2 的 TokenManager 实现
"""

from __future__ import annotations

import json
import random
import string
import time
import urllib.request
from http.cookies import SimpleCookie
from threading import Lock
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:
    yaml = None


class MsTokenManager:
    """
    msToken 生成器：
    1) 优先尝试从 mssdk 接口生成真实 msToken
    2) 失败时回退到随机 msToken，保证请求参数完整
    """

    F2_CONF_URL = (
        "https://raw.githubusercontent.com/Johnserf-Seed/f2/main/f2/conf/conf.yaml"
    )
    _cached_conf: Optional[Dict[str, Any]] = None
    _cached_at: float = 0
    _cache_ttl_seconds: int = 3600
    _lock = Lock()

    def __init__(
        self,
        user_agent: str,
        conf_url: Optional[str] = None,
        timeout_seconds: int = 15,
    ):
        self.user_agent = user_agent
        self.conf_url = conf_url or self.F2_CONF_URL
        self.timeout_seconds = timeout_seconds

    @classmethod
    def _is_valid_ms_token(cls, token: Optional[str]) -> bool:
        if not token or not isinstance(token, str):
            return False
        # 与 F2 保持一致，长度通常为 164 或 184
        return len(token.strip()) in (164, 184)

    @classmethod
    def gen_false_ms_token(cls) -> str:
        token = (
            "".join(
                random.choice(string.ascii_letters + string.digits) for _ in range(182)
            )
            + "=="
        )
        return token

    def ensure_ms_token(self, cookies: Dict[str, str]) -> str:
        current = (cookies or {}).get("msToken", "").strip()
        if current:
            return current

        real = self.gen_real_ms_token()
        if real:
            return real

        return self.gen_false_ms_token()

    def gen_real_ms_token(self) -> Optional[str]:
        conf = self._load_f2_ms_token_conf()
        if not conf:
            return None

        payload = {
            "magic": conf["magic"],
            "version": conf["version"],
            "dataType": conf["dataType"],
            "strData": conf["strData"],
            "ulr": conf["ulr"],
            "tspFromClient": int(time.time() * 1000),
        }

        request = urllib.request.Request(
            conf["url"],
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as resp:
                token = self._extract_ms_token_from_headers(resp.headers)
                if self._is_valid_ms_token(token):
                    return token
                if token:
                    pass  # unexpected length
                return None
        except Exception:
            return None

    def _load_f2_ms_token_conf(self) -> Optional[Dict[str, Any]]:
        if yaml is None:
            return None

        now = time.time()
        with self._lock:
            if self._cached_conf and (now - self._cached_at) < self._cache_ttl_seconds:
                return self._cached_conf

        try:
            with urllib.request.urlopen(
                self.conf_url, timeout=self.timeout_seconds
            ) as resp:
                raw = resp.read().decode("utf-8")
                data = yaml.safe_load(raw) or {}
                # 尝试多种路径获取 msToken 配置
                ms_conf = (
                    data.get("f2", {}).get("douyin", {}).get("msToken", {})
                    or data.get("douyin", {}).get("msToken", {})
                    or {}
                )
                required = {"url", "magic", "version", "dataType", "ulr", "strData"}
                if not required.issubset(ms_conf.keys()):
                    return None

                with self._lock:
                    self._cached_conf = ms_conf
                    self._cached_at = now
                return ms_conf
        except Exception:
            return None

    @staticmethod
    def _extract_ms_token_from_headers(headers: Any) -> Optional[str]:
        set_cookies = (
            headers.get_all("Set-Cookie") if hasattr(headers, "get_all") else []
        )
        for header in set_cookies or []:
            cookie = SimpleCookie()
            cookie.load(header)
            morsel = cookie.get("msToken")
            if morsel and morsel.value:
                return morsel.value.strip()
        return None