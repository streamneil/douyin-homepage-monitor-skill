#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音主页监控脚本（重构版）
- 使用 jiji262/douyin-downloader 的核心模块进行 API 调用和签名
- 检测新视频，下载到 ./Download/<用户名>/ 并输出 JSON 通知
- 检测用户昵称/签名/IP归属变化，输出 JSON 通知
- 结果以 JSON Lines 格式输出到 stdout，每行一个通知事件
- 通知类型：new_video | profile_update | init_complete | download_result | error

用法：
  # 增量监控（常规定时调用）
  python monitor.py '{"save_dir":"./Download","targets":[{"label":"xx","url":"https://v.douyin.com/xxx"}]}'

  # 首次初始化（添加新监控目标时调用，只抓列表不下载）
  python monitor.py --init '{"save_dir":"./Download","targets":[{"label":"xx","url":"https://v.douyin.com/xxx"}]}'

  # 按需下载指定视频（用户要求下载某条时调用）
  python monitor.py --download '{"save_dir":"./Download","label":"xx","home_url":"https://v.douyin.com/xxx","indices":[0,1,2]}'
  # indices 是 video_list 中从新到旧排序后的下标（0=最新）

  # 按需下载指定 aweme_id 的视频
  python monitor.py --download '{"save_dir":"./Download","label":"xx","home_url":"https://v.douyin.com/xxx","aweme_ids":["7123456789"]}'

  # API 检测（诊断 Cookie 是否有效）
  python monitor.py --check '{"home_url":"https://v.douyin.com/xxx"}'
"""

import json
import os
import re
import sys
import time
import hashlib
from contextlib import closing
from typing import Dict, List, Optional, Tuple, Any

import requests

# 导入核心库模块
from lib import DouyinAPIClient, sanitize_cookies, parse_cookie_header

# ── 常量 ──────────────────────────────────────────────────────────────────────

# Cookie 配置（必须）：
# 抖音 API 需要完整的浏览器登录 Cookie 才能获取用户视频列表（超过首页约 20 条）。
# 参考 jiji262/douyin-downloader 的 cookie_fetcher：需要 sessionid、sid_tt、sid_guard 等登录字段。
#
# 获取步骤：
#   1. 浏览器打开 https://www.douyin.com 并登录
#   2. F12 → Network → 刷新页面 → 任意请求 → Request Headers → 复制 cookie 字段的完整值
#   3. 粘贴到下方 COOKIE = "" 的引号内
#
# ttwid 和 msToken 会在运行时自动动态获取并覆盖 Cookie 中的旧值。
# Cookie 失效后（通常数月）重复上述步骤更新即可。
COOKIE = ""

# ── Cookie 构建 ────────────────────────────────────────────────────────────────

def _fetch_ttwid() -> str:
    """动态获取 ttwid（无需登录）"""
    try:
        url = 'https://ttwid.bytedance.com/ttwid/union/register/'
        data = ('{"region":"cn","aid":1768,"needFid":false,"service":"www.ixigua.com",'
                '"migrate_info":{"ticket":"","source":"node"},"cbUrlProtocol":"https","union":true}')
        res = requests.post(url, data=data, timeout=8)
        for _, v in res.cookies.items():
            return v
    except Exception:
        pass
    return ''

def _build_runtime_cookies() -> Dict[str, str]:
    """
    构建运行时 Cookie。
    策略（参考 jiji262/douyin-downloader cookie_fetcher 的 SUGGESTED_KEYS）：
    1. 以用户配置的完整登录 Cookie 为基础（需含 sessionid、sid_tt、sid_guard 等）
    2. 动态获取真实 ttwid 并覆盖旧值（字节跳动官方接口，无需登录）
    3. msToken 由 MsTokenManager 在首次请求时自动注入
    """
    cookies: Dict[str, str] = parse_cookie_header(COOKIE) if COOKIE else {}

    # 基础设备标识（若 Cookie 中不存在则补充）
    cookies.setdefault('device_web_cpu_core', '8')
    cookies.setdefault('device_web_memory_size', '8')

    # 动态获取 ttwid 并覆盖（保证新鲜度）
    ttwid = _fetch_ttwid()
    if ttwid:
        sys.stderr.write(f'[auth] ttwid 获取成功: {ttwid[:20]}...\n')
        cookies['ttwid'] = ttwid
    else:
        sys.stderr.write('[auth] ttwid 获取失败，将使用 Cookie 中的旧值\n')

    if not COOKIE:
        sys.stderr.write('[auth] 警告：COOKIE 未配置，无登录态下 API 将只返回有限数据\n')

    return sanitize_cookies(cookies)

# ── API 客户端 ──────────────────────────────────────────────────────────────────

_API_CLIENT: Optional[DouyinAPIClient] = None

def get_api_client() -> DouyinAPIClient:
    """获取 API 客户端（单例，延迟初始化）"""
    global _API_CLIENT
    if _API_CLIENT is None:
        _API_CLIENT = DouyinAPIClient(cookies=_build_runtime_cookies())
    return _API_CLIENT

# ── Cookie 有效性检测 ──────────────────────────────────────────────────────────

def check_login_status() -> bool:
    """检测 COOKIE 变量中是否包含登录态字段（sessionid + uid_tt）"""
    if not COOKIE:
        return False
    session_match = re.search(r'sessionid=([^;]+)', COOKIE)
    uid_match = re.search(r'uid_tt=([^;]+)', COOKIE)
    session_id = session_match.group(1).strip() if session_match else ''
    uid_tt = uid_match.group(1).strip() if uid_match else ''
    return bool(session_id and len(session_id) >= 20 and uid_tt)

# ── 文件存储 ───────────────────────────────────────────────────────────────────

def _url_md5(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def _aweme_file(home_url: str) -> str:
    return _url_md5(home_url) + '-aweme.history'

def _profile_file(home_url: str) -> str:
    return _url_md5(home_url) + '-userprofile.history'

def _catalog_file(home_url: str) -> str:
    """视频目录缓存文件，存储全量视频列表（含下载 URL），供按需下载使用"""
    return _url_md5(home_url) + '-catalog.json'

def load_history(home_url: str) -> set:
    path = _aweme_file(home_url)
    if not os.path.exists(path):
        return set()
    with open(path, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def save_history(home_url: str, aweme_id: str):
    with open(_aweme_file(home_url), 'a', encoding='utf-8') as f:
        f.write(aweme_id.strip() + '\n')

def load_profile(home_url: str) -> Dict[str, str]:
    path = _profile_file(home_url)
    result = {'nickname': '', 'signature': '', 'ip_location': '', 'sec_uid': ''}
    if not os.path.exists(path):
        return result
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ':' in line:
                    k, v = line.split(':', 1)
                    if k in result:
                        result[k] = v
    except Exception:
        pass
    return result

def save_profile(home_url: str, nickname: str, signature: str, ip_location: str, sec_uid: str = ''):
    path = _profile_file(home_url)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'nickname:{nickname}\nsignature:{signature}\nip_location:{ip_location}\nsec_uid:{sec_uid}\n')

def save_catalog(home_url: str, video_list: List[Dict[str, Any]]):
    """保存视频目录（含 aweme_id）到本地缓存，供按需下载使用"""
    path = _catalog_file(home_url)
    # 只保存必要字段，不保存 video_url（因为会过期）
    catalog_data = [
        {
            'aweme_id': v['aweme_id'],
            'title': v.get('title', ''),
            'desc': v.get('desc', ''),
            'create_time': v.get('create_time', ''),
            'date': v.get('date', ''),
            'digg_count': v.get('digg_count', 0),
            'cover_url': v.get('cover_url', ''),
        }
        for v in video_list
    ]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(catalog_data, f, ensure_ascii=False, indent=2)

def load_catalog(home_url: str) -> List[Dict[str, Any]]:
    """读取本地视频目录缓存，返回列表（从新到旧）；不存在则返回 []"""
    path = _catalog_file(home_url)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

# ── 抖音 API ───────────────────────────────────────────────────────────────────

def get_sec_uid(home_url: str) -> str:
    """从短链/主页 URL 获取 sec_uid（先读缓存，否则发起 HTTP 解析）"""
    # 读取缓存
    cached = load_profile(home_url).get('sec_uid', '')
    if cached:
        return cached

    client = get_api_client()
    sec_uid = client.get_sec_uid_from_url(home_url)
    if not sec_uid:
        raise ValueError(f"无法从 URL 解析 sec_uid: {home_url}")
    return sec_uid

def get_user_profile(sec_uid: str) -> Tuple[str, str, str]:
    """获取用户资料"""
    client = get_api_client()
    user = client.get_user_info(sec_uid)
    if not user:
        raise ValueError(f"无法获取用户信息: {sec_uid}")
    nickname = user.get('nickname', '')
    signature = user.get('signature', '')
    ip_location = user.get('ip_location', '')
    return nickname, signature, ip_location

def fetch_video_page(sec_uid: str, max_cursor: int = 0) -> Tuple[List[Dict], int, bool]:
    """获取一页视频列表"""
    client = get_api_client()
    result = client.get_user_post(sec_uid, max_cursor=max_cursor, count=20)
    items = result.get('aweme_list') or []
    next_cursor = result.get('max_cursor', 0)
    has_more = result.get('has_more', False)
    return items, next_cursor, has_more

def fetch_all_videos(sec_uid: str) -> List[Dict[str, Any]]:
    """翻页获取全部视频，返回所有 aweme item 列表（原始 API 数据）"""
    all_items = []
    max_cursor = 0
    has_more = True
    attempts = 0

    while has_more and attempts < 50:
        attempts += 1
        try:
            items, max_cursor, has_more = fetch_video_page(sec_uid, max_cursor)
        except Exception as e:
            sys.stderr.write(f'[monitor] 获取视频页失败 (第{attempts}页): {e}\n')
            break

        if not items:
            break

        all_items.extend(items)
        sys.stderr.write(f'[monitor] 已获取 {len(all_items)} 条视频...\n')

        if has_more:
            time.sleep(0.5)

    return all_items

def parse_video(item: Dict[str, Any]) -> Dict[str, Any]:
    """从 aweme item 提取关键字段"""
    ts = item.get('create_time', 0)
    dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts)) if ts else ''
    date_prefix = time.strftime('%Y-%m-%d', time.localtime(ts)) if ts else ''
    raw_desc = item.get('desc', '') or ''
    safe_desc = re.sub(r'[\\/:*?"<>|]', '', raw_desc) or '无标题'
    
    title = f'[{date_prefix}] {safe_desc}'
    
    # 提取封面 URL
    cover_url = ''
    cover = item.get('video', {}).get('cover', {})
    cover_urls = cover.get('url_list') or []
    if cover_urls:
        cover_url = cover_urls[0]
    
    # 提取点赞数
    stats = item.get('statistics') or {}
    digg_count = stats.get('digg_count', 0)
    
    return {
        'aweme_id': item.get('aweme_id', ''),
        'title': title,
        'desc': safe_desc,
        'create_time': dt,
        'date': date_prefix,
        'cover_url': cover_url,
        'digg_count': digg_count,
    }

# ── 视频下载 ───────────────────────────────────────────────────────────────────

def get_video_download_url(aweme_id: str) -> Optional[Tuple[str, Dict[str, str]]]:
    """
    获取视频下载 URL（实时刷新）
    
    通过 get_video_detail 获取最新的 aweme 数据，然后提取下载链接
    """
    client = get_api_client()
    detail = client.get_video_detail(aweme_id)
    if not detail:
        return None
    return client.build_video_download_url(detail)

def download_video(aweme_id: str, dest_path: str) -> str:
    """
    下载视频到 dest_path（不含扩展名），返回实际文件路径。
    
    使用 DouyinAPIClient 获取实时下载链接，绕过 CDN 防盗链。
    """
    mp4_path = dest_path + '.mp4'
    
    # 获取下载 URL
    url_headers = get_video_download_url(aweme_id)
    if not url_headers:
        raise ValueError(f'无法获取视频下载链接: {aweme_id}')
    
    video_url, headers = url_headers
    sys.stderr.write(f'[download] 获取到下载 URL: {video_url[:80]}...\n')
    
    # 下载视频
    with closing(requests.get(video_url, headers=headers, stream=True, timeout=120, 
                              allow_redirects=True)) as r:
        r.raise_for_status()
        content_type = r.headers.get('content-type', '')
        if 'text' in content_type or 'html' in content_type:
            raise ValueError(f'返回内容不是视频（content-type: {content_type}）')
        
        total = int(r.headers.get('content-length', 0))
        done = 0
        with open(mp4_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done / total * 100
                        sys.stderr.write(f'\r  下载进度: {pct:.1f}% ({done/1024/1024:.1f}MB)')
        sys.stderr.write('\n')
    
    # 验证文件大小
    file_size = os.path.getsize(mp4_path)
    if file_size < 10240:
        os.remove(mp4_path)
        raise ValueError(f'下载的文件过小（{file_size} bytes）')
    
    return mp4_path

# ── 事件输出 ───────────────────────────────────────────────────────────────────

def emit(event: Dict[str, Any]):
    """将事件以 JSON Lines 格式输出到 stdout"""
    print(json.dumps(event, ensure_ascii=False), flush=True)

# ── 首次初始化模式 ───────────────────────────────────────────────────────────────

def init_one(label: str, home_url: str, save_dir: str):
    """
    首次添加监控目标时调用：
    1. 获取用户资料
    2. 全量抓取所有视频列表（翻页到底）
    3. 将视频目录保存到本地缓存，写入历史记录
    4. 输出 init_complete 事件
    """
    sys.stderr.write(f'[init] 开始初始化: {label} ({home_url})\n')

    # 1. 检测登录态，未登录时提前警告
    is_logged_in = check_login_status()
    if not is_logged_in:
        emit({
            'type': 'error',
            'code': 'cookie_invalid',
            'label': label,
            'message': (
                'Cookie 未配置或缺少登录字段（sessionid/uid_tt）。'
                '抖音 API 需要登录态才能获取完整视频列表，'
                '请更新 scripts/monitor.py 中的 COOKIE 变量后重试。'
            )
        })
        sys.stderr.write('[init] 警告：Cookie 未登录，继续尝试但结果可能不完整\n')

    # 2. 获取 sec_uid
    try:
        sec_uid = get_sec_uid(home_url)
        sys.stderr.write(f'[init] sec_uid: {sec_uid}\n')
    except Exception as e:
        emit({'type': 'error', 'code': 'sec_uid_failed', 'label': label, 'message': str(e)})
        return

    # 3. 获取用户资料
    try:
        nickname, signature, ip_location = get_user_profile(sec_uid)
        sys.stderr.write(f'[init] 用户: {nickname} ({ip_location})\n')
    except Exception as e:
        emit({'type': 'error', 'code': 'profile_failed', 'label': label, 'message': str(e)})
        return

    save_profile(home_url, nickname, signature, ip_location, sec_uid)

    # 4. 全量抓取视频列表
    sys.stderr.write(f'[init] 开始全量抓取视频列表...\n')
    all_items = fetch_all_videos(sec_uid)
    total_count = len(all_items)
    sys.stderr.write(f'[init] 共获取到 {total_count} 条视频\n')

    # 5. 解析视频列表，写入历史记录，保存目录缓存
    user_dir = os.path.join(save_dir, nickname)
    os.makedirs(user_dir, exist_ok=True)

    video_list = []
    for item in all_items:
        v = parse_video(item)
        video_list.append(v)
        save_history(home_url, v['aweme_id'])

    # 按发布时间从新到旧排序
    video_list.sort(key=lambda x: x.get('create_time', ''), reverse=True)

    # 保存目录缓存（不含 video_url，因为会过期）
    save_catalog(home_url, video_list)

    # 6. 输出 init_complete 事件
    display_list = [
        {
            'aweme_id': v['aweme_id'],
            'title': v.get('desc', ''),
            'create_time': v.get('create_time', ''),
            'date': v.get('date', ''),
            'digg_count': v.get('digg_count', 0),
            'cover_url': v.get('cover_url', ''),
            'file_path': '',
        }
        for v in video_list
    ]

    emit({
        'type': 'init_complete',
        'label': label,
        'nickname': nickname,
        'signature': signature,
        'ip_location': ip_location,
        'save_dir': user_dir,
        'total_videos': total_count,
        'video_list': display_list,
        'login_warning': not is_logged_in,
        'message': (
            f'{label}（{nickname}）初始化完成：'
            f'共 {total_count} 条视频已记录，视频目录已缓存。'
            f'使用 --download 模式可按需下载任意视频。'
        )
    })

# ── 按需下载模式 ───────────────────────────────────────────────────────────────

def download_one(label: str, home_url: str, save_dir: str, 
                 indices: Optional[List[int]] = None, 
                 aweme_ids: Optional[List[str]] = None):
    """
    按需下载指定视频。
    使用 aweme_id 实时获取下载链接，解决缓存 URL 过期问题。
    """
    sys.stderr.write(f'[download] 开始按需下载: {label}\n')

    # 读取本地目录缓存
    catalog = load_catalog(home_url)

    if not catalog:
        # 缓存不存在，重新从 API 获取
        sys.stderr.write('[download] 本地缓存不存在，重新从 API 获取视频列表...\n')
        try:
            sec_uid = get_sec_uid(home_url)
            nickname, _, _ = get_user_profile(sec_uid)
            all_items = fetch_all_videos(sec_uid)
            catalog = [parse_video(item) for item in all_items]
            catalog.sort(key=lambda x: x.get('create_time', ''), reverse=True)
            save_catalog(home_url, catalog)
        except Exception as e:
            emit({'type': 'error', 'code': 'catalog_failed', 'label': label, 'message': str(e)})
            return
    else:
        profile = load_profile(home_url)
        nickname = profile.get('nickname') or label

    # 确定要下载哪些视频
    targets = []
    if aweme_ids:
        id_set = set(aweme_ids)
        targets = [v for v in catalog if v['aweme_id'] in id_set]
        if not targets:
            emit({
                'type': 'error', 'code': 'not_found', 'label': label,
                'message': f'未找到指定的 aweme_id: {aweme_ids}'
            })
            return
    elif indices is not None:
        for idx in indices:
            if 0 <= idx < len(catalog):
                targets.append(catalog[idx])
            else:
                emit({
                    'type': 'error', 'code': 'index_out_of_range', 'label': label,
                    'message': f'下标 {idx} 超出范围（共 {len(catalog)} 条视频，下标从 0 开始）'
                })
        if not targets:
            return
    else:
        emit({'type': 'error', 'code': 'no_target', 'label': label, 'message': '未指定要下载的视频'})
        return

    user_dir = os.path.join(save_dir, nickname)
    os.makedirs(user_dir, exist_ok=True)

    for v in targets:
        aweme_id = v['aweme_id']
        title = v.get('title', v.get('desc', ''))
        dest = os.path.join(user_dir, title)
        mp4_path = dest + '.mp4'

        # 已存在则跳过
        if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 10240:
            sys.stderr.write(f'[download] 已存在，跳过: {title}\n')
            emit({
                'type': 'download_result',
                'label': label,
                'nickname': nickname,
                'aweme_id': aweme_id,
                'title': v.get('desc', ''),
                'create_time': v.get('create_time', ''),
                'digg_count': v.get('digg_count', 0),
                'cover_url': v.get('cover_url', ''),
                'file_path': mp4_path,
                'skipped': True,
            })
            continue

        try:
            sys.stderr.write(f'[download] 下载: {title} (aweme_id: {aweme_id})\n')
            file_path = download_video(aweme_id, dest)
            emit({
                'type': 'download_result',
                'label': label,
                'nickname': nickname,
                'aweme_id': aweme_id,
                'title': v.get('desc', ''),
                'create_time': v.get('create_time', ''),
                'digg_count': v.get('digg_count', 0),
                'cover_url': v.get('cover_url', ''),
                'file_path': file_path,
                'skipped': False,
            })
        except Exception as e:
            sys.stderr.write(f'[download] 下载失败: {title} — {e}\n')
            emit({
                'type': 'error',
                'code': 'download_failed',
                'label': label,
                'aweme_id': aweme_id,
                'title': v.get('desc', ''),
                'message': str(e),
            })

# ── 增量监控模式 ───────────────────────────────────────────────────────────────

def monitor_one(label: str, home_url: str, save_dir: str):
    """
    增量监控单个主页，只处理历史记录中没有的新视频，并下载。
    """
    sys.stderr.write(f'[monitor] 开始处理: {label} ({home_url})\n')

    try:
        sec_uid = get_sec_uid(home_url)
    except Exception as e:
        sys.stderr.write(f'[monitor] 获取 sec_uid 失败: {e}\n')
        return

    try:
        nickname, signature, ip_location = get_user_profile(sec_uid)
    except Exception as e:
        sys.stderr.write(f'[monitor] 获取用户资料失败: {e}\n')
        return

    old_profile = load_profile(home_url)
    if old_profile['nickname']:
        changes = []
        if old_profile['nickname'] != nickname:
            changes.append(f'昵称: {old_profile["nickname"]} → {nickname}')
        if old_profile['signature'] != signature:
            changes.append(f'签名: {old_profile["signature"]} → {signature}')
        if old_profile['ip_location'] != ip_location:
            changes.append(f'IP归属: {old_profile["ip_location"]} → {ip_location}')
        if changes:
            emit({
                'type': 'profile_update',
                'label': label,
                'nickname': nickname,
                'changes': changes,
                'message': f'{label} 更新了主页信息：' + '；'.join(changes),
            })
    save_profile(home_url, nickname, signature, ip_location, sec_uid)

    history = load_history(home_url)
    new_videos = []

    # 只取第一页（定时监控场景：正常情况新视频只会出现在最前面）
    # 若第一页全部都是新视频（极端情况：用户一次发布超过 20 条），继续翻页直到遇到已知视频
    max_cursor = 0
    has_more = True
    attempts = 0

    while has_more and attempts < 5:
        attempts += 1
        try:
            items, max_cursor, has_more = fetch_video_page(sec_uid, max_cursor)
        except Exception as e:
            sys.stderr.write(f'[monitor] 获取视频页失败: {e}\n')
            break

        if not items:
            break

        parsed = [parse_video(i) for i in items]
        page_new = [v for v in parsed if v.get('aweme_id') and v['aweme_id'] not in history]
        new_videos.extend(page_new)

        # 本页出现已知视频，说明已到达历史边界，停止翻页
        if any(v.get('aweme_id') in history for v in parsed):
            break

    if not new_videos:
        sys.stderr.write(f'[monitor] {label}: 无新视频\n')
        emit({
            'type': 'monitor_summary',
            'label': label,
            'nickname': nickname,
            'new_count': 0,
        })
        return

    user_dir = os.path.join(save_dir, nickname)
    os.makedirs(user_dir, exist_ok=True)

    downloaded_count = 0
    for v in reversed(new_videos):
        aweme_id = v['aweme_id']
        title = v.get('title', v.get('desc', ''))
        dest = os.path.join(user_dir, title)

        try:
            sys.stderr.write(f'[monitor] 下载新视频: {title}\n')
            file_path = download_video(aweme_id, dest)
            save_history(home_url, aweme_id)
            downloaded_count += 1
        except Exception as e:
            sys.stderr.write(f'[monitor] 下载失败: {e}\n')
            file_path = ''

        emit({
            'type': 'new_video',
            'label': label,
            'nickname': nickname,
            'aweme_id': aweme_id,
            'title': v.get('desc', ''),
            'create_time': v.get('create_time', ''),
            'cover_url': v.get('cover_url', ''),
            'digg_count': v.get('digg_count', 0),
            'file_path': file_path,
        })

    # 将新视频 prepend 到 catalog，保持目录实时更新
    if downloaded_count > 0:
        catalog = load_catalog(home_url)
        known_ids = {v['aweme_id'] for v in catalog}
        new_entries = [
            {
                'aweme_id': v['aweme_id'],
                'title': v.get('desc', ''),
                'desc': v.get('desc', ''),
                'create_time': v.get('create_time', ''),
                'date': v.get('date', ''),
                'digg_count': v.get('digg_count', 0),
                'cover_url': v.get('cover_url', ''),
            }
            for v in new_videos if v['aweme_id'] not in known_ids
        ]
        if new_entries:
            save_catalog(home_url, new_entries + catalog)

    emit({
        'type': 'monitor_summary',
        'label': label,
        'nickname': nickname,
        'new_count': len(new_videos),
    })

# ── API 检测模式 ─────────────────────────────────────────────────────────────────

def check_api(home_url: str):
    """
    检测 API 是否正常工作，用于诊断 Cookie 是否有效。
    """
    sys.stderr.write(f'[check] 开始检测: {home_url}\n')

    try:
        sec_uid = get_sec_uid(home_url)
        sys.stderr.write(f'[check] sec_uid: {sec_uid}\n')
    except Exception as e:
        emit({
            'type': 'check_api',
            'success': False,
            'message': f'获取 sec_uid 失败: {e}'
        })
        return

    try:
        nickname, signature, ip_location = get_user_profile(sec_uid)
        sys.stderr.write(f'[check] 用户: {nickname}\n')
    except Exception as e:
        emit({
            'type': 'check_api',
            'success': False,
            'message': f'获取用户信息失败: {e}'
        })
        return

    try:
        items, _, _ = fetch_video_page(sec_uid)
        count = len(items)
        sys.stderr.write(f'[check] 第一页视频数: {count}\n')
    except Exception as e:
        emit({
            'type': 'check_api',
            'success': False,
            'message': f'获取视频列表失败: {e}'
        })
        return

    emit({
        'type': 'check_api',
        'success': True,
        'nickname': nickname,
        'ip_location': ip_location,
        'first_page_count': count,
        'message': f'✅ API 正常工作：{nickname}，第一页 {count} 条视频'
    })

# ── 主入口 ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        sys.stderr.write('用法: python monitor.py [options] <json_config>\n')
        sys.stderr.write('选项:\n')
        sys.stderr.write('  --init     首次初始化（只抓列表不下载）\n')
        sys.stderr.write('  --download 按需下载指定视频\n')
        sys.stderr.write('  --check    检测 API 是否正常\n')
        sys.exit(1)

    mode = 'monitor'
    if sys.argv[1] == '--init':
        mode = 'init'
        config_str = sys.argv[2] if len(sys.argv) > 2 else ''
    elif sys.argv[1] == '--download':
        mode = 'download'
        config_str = sys.argv[2] if len(sys.argv) > 2 else ''
    elif sys.argv[1] == '--check':
        mode = 'check'
        config_str = sys.argv[2] if len(sys.argv) > 2 else ''
    else:
        config_str = sys.argv[1]

    if not config_str:
        sys.stderr.write('错误: 需要提供 JSON 配置\n')
        sys.exit(1)

    try:
        config = json.loads(config_str)
    except json.JSONDecodeError as e:
        sys.stderr.write(f'JSON 解析失败: {e}\n')
        sys.exit(1)

    save_dir = config.get('save_dir', './Download')

    if mode == 'init':
        targets = config.get('targets', [])
        for target in targets:
            label = target.get('label', '')
            url = target.get('url', '')
            if label and url:
                init_one(label, url, save_dir)

    elif mode == 'download':
        label = config.get('label', '')
        home_url = config.get('home_url', '')
        indices = config.get('indices')
        aweme_ids = config.get('aweme_ids')
        if label and home_url:
            download_one(label, home_url, save_dir, indices, aweme_ids)

    elif mode == 'check':
        home_url = config.get('home_url', '')
        if home_url:
            check_api(home_url)

    else:
        targets = config.get('targets', [])
        for target in targets:
            label = target.get('label', '')
            url = target.get('url', '')
            if label and url:
                monitor_one(label, url, save_dir)


if __name__ == '__main__':
    main()