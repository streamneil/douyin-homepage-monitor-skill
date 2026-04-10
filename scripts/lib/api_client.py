# -*- coding: utf-8 -*-
"""
抖音 API 客户端（同步版本）
基于 jiji262/douyin-downloader core/api_client.py
"""

import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests

from .xbogus import XBogus
from .ms_token_manager import MsTokenManager
from .cookie_utils import sanitize_cookies, parse_cookie_header


_USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]


class DouyinAPIClient:
    BASE_URL = "https://www.douyin.com"

    def __init__(self, cookies: Optional[Dict[str, str]] = None, cookie_str: Optional[str] = None):
        """
        初始化 API 客户端
        
        Args:
            cookies: Cookie 字典
            cookie_str: Cookie 字符串（如从浏览器复制）
        """
        if cookies:
            self.cookies = sanitize_cookies(cookies)
        elif cookie_str:
            self.cookies = parse_cookie_header(cookie_str)
        else:
            self.cookies = {}

        self._user_agent = random.choice(_USER_AGENT_POOL)
        self.headers = {
            "User-Agent": self._user_agent,
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        self._signer = XBogus(self._user_agent)
        self._ms_token_manager = MsTokenManager(user_agent=self._user_agent)

    def _ensure_ms_token(self) -> str:
        """确保 msToken 存在"""
        current = self.cookies.get("msToken", "").strip()
        if current:
            return current
        token = self._ms_token_manager.ensure_ms_token(self.cookies)
        self.cookies["msToken"] = token
        return token

    def _default_query(self) -> Dict[str, Any]:
        """构建默认请求参数"""
        ms_token = self._ensure_ms_token()
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "version_code": "290100",
            "version_name": "29.1.0",
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "130.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "130.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "12",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "100",
            "msToken": ms_token,
        }

    def sign_url(self, url: str) -> Tuple[str, str]:
        """使用 XBogus 对 URL 进行签名"""
        signed_url, _xbogus, ua = self._signer.build(url)
        return signed_url, ua

    def build_signed_path(self, path: str, params: Dict[str, Any]) -> Tuple[str, str]:
        """构建带签名的请求路径"""
        query = urlencode(params)
        base_url = f"{self.BASE_URL}{path}?{query}"
        return self.sign_url(base_url)

    def _request_json(
        self,
        path: str,
        params: Dict[str, Any],
        *,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """发送带签名请求并返回 JSON"""
        delays = [1, 2, 5]
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            signed_url, ua = self.build_signed_path(path, params)
            headers = dict(self.headers)
            headers["User-Agent"] = ua

            try:
                response = requests.get(
                    signed_url,
                    headers=headers,
                    cookies=self.cookies,
                    timeout=15,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data if isinstance(data, dict) else {}
                if response.status_code < 500 and response.status_code != 429:
                    return {}
                last_error = RuntimeError(f"HTTP {response.status_code}")
            except Exception as exc:
                last_error = exc

            if attempt < max_retries - 1:
                delay = delays[min(attempt, len(delays) - 1)]
                time.sleep(delay)

        return {}

    def get_user_info(self, sec_uid: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        params = self._default_query()
        params["sec_user_id"] = sec_uid
        data = self._request_json("/aweme/v1/web/user/profile/other/", params)
        if data:
            return data.get("user")
        return None

    def get_user_post(
        self, sec_uid: str, max_cursor: int = 0, count: int = 20
    ) -> Dict[str, Any]:
        """获取用户发布的视频列表"""
        params = self._default_query()
        params.update({
            "sec_user_id": sec_uid,
            "max_cursor": max_cursor,
            "count": count,
            "locate_query": "false",
            "show_live_replay_strategy": "1",
            "need_time_list": "1",
            "time_list_query": "0",
            "whale_cut_token": "",
            "cut_version": "1",
            "publish_video_strategy_type": "2",
        })
        raw = self._request_json("/aweme/v1/web/aweme/post/", params)
        return self._normalize_paged_response(raw)

    def get_video_detail(self, aweme_id: str) -> Optional[Dict[str, Any]]:
        """获取视频详情（包含下载链接）"""
        # 尝试不同的 aid 值
        for aid in ("6383", "1128"):
            params = self._default_query()
            params.update({
                "aweme_id": aweme_id,
                "aid": aid,
            })
            data = self._request_json("/aweme/v1/web/aweme/detail/", params)
            if not data:
                continue
            detail = data.get("aweme_detail")
            if detail:
                return detail
            # 检查是否被过滤
            filter_info = data.get("filter_detail")
            if isinstance(filter_info, dict) and filter_info.get("filter_reason"):
                continue
            break
        return None

    def resolve_short_url(self, short_url: str) -> Optional[str]:
        """解析短链接获取真实 URL（包含 sec_uid）"""
        try:
            response = requests.get(
                short_url,
                headers=self.headers,
                cookies=self.cookies,
                allow_redirects=True,
                timeout=10,
            )
            return str(response.url)
        except Exception:
            return None

    def get_sec_uid_from_url(self, url: str) -> Optional[str]:
        """从 URL（短链或主页）提取 sec_uid"""
        # 先解析短链
        real_url = self.resolve_short_url(url) or url
        match = re.search(r"sec_uid=([^&]+)", real_url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _normalize_paged_response(raw_data: Any) -> Dict[str, Any]:
        """标准化分页响应"""
        raw = raw_data if isinstance(raw_data, dict) else {}
        
        items: List[Dict[str, Any]] = []
        for key in ["aweme_list", "items"]:
            value = raw.get(key)
            if isinstance(value, list):
                items = value
                break

        has_more_value = raw.get("has_more", False)
        try:
            has_more = bool(int(has_more_value))
        except (TypeError, ValueError):
            has_more = bool(has_more_value)

        max_cursor_value = raw.get("max_cursor") or raw.get("cursor", 0)
        try:
            max_cursor = int(max_cursor_value or 0)
        except (TypeError, ValueError):
            max_cursor = 0

        return {
            "items": items,
            "aweme_list": items,
            "has_more": has_more,
            "max_cursor": max_cursor,
            "raw": raw,
        }

    def build_video_download_url(self, aweme_data: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, str]]]:
        """
        从 aweme 数据构建视频下载 URL
        
        参考 jiji262/douyin-downloader downloader_base.py 的 _build_no_watermark_url
        
        Returns:
            (video_url, headers) 或 None
        """
        video = aweme_data.get("video", {})
        play_addr = video.get("play_addr", {})
        url_candidates = [c for c in (play_addr.get("url_list") or []) if c]
        
        # 优先选择无水印 URL
        url_candidates.sort(key=lambda u: 0 if "watermark=0" in u else 1)
        
        headers = {
            "Referer": f"{self.BASE_URL}/",
            "Origin": self.BASE_URL,
            "User-Agent": self._user_agent,
        }

        fallback_candidate: Optional[Tuple[str, Dict[str, str]]] = None
        
        for candidate in url_candidates:
            # 对于抖音域名，需要签名
            if "douyin.com" in candidate and "X-Bogus=" not in candidate:
                signed_url, ua = self.sign_url(candidate)
                headers["User-Agent"] = ua
                return signed_url, headers
            # CDN 直链（如 douyinvod.com）可以直接使用
            if "douyinvod.com" in candidate or "bytecdn.cn" in candidate:
                return candidate, headers
            fallback_candidate = (candidate, headers)

        if fallback_candidate:
            return fallback_candidate

        # 尝试使用 uri 构建
        uri = play_addr.get("uri") or video.get("vid")
        if uri:
            params = {
                "video_id": uri,
                "ratio": "1080p",
                "line": "0",
                "is_play_url": "1",
                "watermark": "0",
            }
            signed_url, ua = self.build_signed_path("/aweme/v1/play/", params)
            headers["User-Agent"] = ua
            return signed_url, headers

        return None