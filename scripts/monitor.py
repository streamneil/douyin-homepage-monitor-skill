#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音主页监控脚本
- 检测新视频，下载到 ./Download/<用户名>/ 并输出 JSON 通知
- 检测用户昵称/签名/IP归属变化，输出 JSON 通知
- 结果以 JSON Lines 格式输出到 stdout，每行一个通知事件
- 通知类型：new_video | profile_update | init_complete | error

用法：
  # 增量监控（常规定时调用）
  python monitor.py '{"save_dir":"./Download","targets":[{"label":"xx","url":"https://v.douyin.com/xxx"}]}'

  # 首次初始化（添加新监控目标时调用，全量抓取+下载历史视频）
  python monitor.py --init '{"save_dir":"./Download","targets":[{"label":"xx","url":"https://v.douyin.com/xxx"}]}'
"""

import re, requests, json, sys, os, time, hashlib, base64
from contextlib import closing

# ── 常量 ──────────────────────────────────────────────────────────────────────

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"

# 请将此 COOKIE 替换为从浏览器抖音网页版复制的最新值
# 打开 https://www.douyin.com → F12 → Network → 任意请求 → Request Headers → cookie
# ⚠️  Cookie 失效是获取视频列表不完整的最常见原因，请保持更新
COOKIE = "douyin.com; device_web_cpu_core=8; device_web_memory_size=8; csrf_session_id=14825116dc9c2fcd63d4632119bc532c; FORCE_LOGIN=%7B%22videoConsumedRemainSeconds%22%3A180%7D; xgplayer_user_id=571413576421; xg_device_score=6.792332233647336; passport_csrf_token=7e267631ddc818b02128b8c7e08f294a; passport_csrf_token_default=7e267631ddc818b02128b8c7e08f294a; bd_ticket_guard_client_web_domain=2; SEARCH_RESULT_LIST_TYPE=%22single%22; download_guide=%223%2F20240507%2F0%22; volume_info=%7B%22isUserMute%22%3Afalse%2C%22isMute%22%3Atrue%2C%22volume%22%3A0.5%7D; pwa2=%220%7C0%7C3%7C0%22; ttwid=1%7Ctszc2J_dOM7jx_4PCBZRSCJxUKi5I4i2Nr9wbDnFcug%7C1715154044%7C88fcb9e48adcf9bde355bf1fee18944e5a1021d415d465734b31a82e20fb91dc; xgplayer_device_id=35940013617; d_ticket=67d954e5df833256ebcd2fc59d5aff4154e38; odin_tt=4f6cc09deb42a3125cf0dea9783bcaf20c4ca064978825d6d42c3dcad395581749e266990b98b09807cc83e935c25f86e3611fe01e62685c3d16883d4d22be3f; passport_assist_user=CkEuJUi8ALBdSpvLAsYaK9YrnGMEwuvMzRpFuHlfHatDzvm8cWky2du-OWo801eRNNCqgsAI1uiSzxIOekE11f0AUBpKCjzJ7QgCPIOp8i11d5cdpE1jYDbjQOZ5azOqKML28BtPcARRQnH37tRD3tBYdTj3YuauEHGz4XSXeR1BpSUQkvbQDRiJr9ZUIAEiAQPnNCmn; n_mh=_QbRJA7TRnnvOnh2XfgXThpiklCKGc1RCDDX8HAsJjU; passport_auth_status=dc33df43ccce4674112c996ad1f3359a%2C941150a1c20a7bd3548cefab4d816c89; passport_auth_status_ss=dc33df43ccce4674112c996ad1f3359a%2C941150a1c20a7bd3548cefab4d816c89; sid_guard=d2a76c9db9e8d914fda02be1e608d287%7C1715336743%7C5184000%7CTue%2C+09-Jul-2024+10%3A25%3A43+GMT; uid_tt=8f6f72b1323ae8dec49d595d16657b68; uid_tt_ss=8f6f72b1323ae8dec49d595d16657b68; sid_tt=d2a76c9db9e8d914fda02be1e608d287; sessionid=d2a76c9db9e8d914fda02be1e608d287; sessionid_ss=d2a76c9db9e8d914fda02be1e608d287; msToken=gKn58dVmX7RgljlSJ6HJ94Y4zIrSzLuTQg17b4GtTj1HGkJdtLO2ED2_Qf2YY93Ie_y2SM1LSrHez8i9PO2XPGpxwLUJyTnRtxMq4f8Ekx2kv53K6XLRIQdmdDmLcNE=; IsDouyinActive=true"

DEFAULT_PAYLOAD_SUFFIX = "device_platform=webapp&aid=6383&channel=channel_pc_web&publish_video_strategy_type=2&source=channel_pc_web&personal_center_strategy=1&update_version_code=170400&pc_client_type=1&version_code=170400&version_name=17.4.0&cookie_enabled=true&screen_width=853&screen_height=1280&browser_language=en&browser_platform=MacIntel&browser_name=Chrome&browser_version=120.0.0.0&browser_online=true&engine_name=Blink&engine_version=120.0.0.0&os_name=Windows&os_version=10&cpu_core_num=8&device_memory=8&platform=PC&downlink=1.25&effective_type=3g&round_trip_time=250&webid=7363610890434774591&msToken=VDd-lnvmJ5sh8YUvkpm6rcozUMIL_FmRtQvY-BsyEZhAR0_rdOSA5hnHeNqQrtqfztN388mOQ4At6M4t-HUe6JMPEWvYbt8BJUTQUc87511FFs9dnbHAfO6dII4BTA=="

DEFAULT_HEADER = {
    'User-Agent': UA,
    'referer': 'https://www.douyin.com/',
    'accept-encoding': None,
    'Cookie': COOKIE
}

USER_POST_URL    = 'https://www.douyin.com/aweme/v1/web/aweme/post/?'
USER_PROFILE_URL = 'https://www.douyin.com/aweme/v1/web/user/profile/other/?'

# ── X-Bogus 签名 ───────────────────────────────────────────────────────────────

def _rc4(key_arr, data_str):
    d = list(range(256))
    c = 0
    result = bytearray(len(data_str))
    for i in range(256):
        c = (c + d[i] + ord(key_arr[i % len(key_arr)])) % 256
        d[i], d[c] = d[c], d[i]
    t = c = 0
    for i in range(len(data_str)):
        t = (t + 1) % 256
        c = (c + d[t]) % 256
        d[t], d[c] = d[c], d[t]
        result[i] = ord(data_str[i]) ^ d[(d[t] + d[c]) % 256]
    return result

def _get_arr2(payload, ua):
    md5 = lambda b: hashlib.md5(b).digest()
    salt_payload = list(md5(md5(payload.encode())))
    salt_form    = list(md5(md5(b'')))  # form='' always
    ua_key = ['\x00', '\x01', '\x0e']
    salt_ua = list(md5(base64.b64encode(_rc4(ua_key, ua))))
    ts = int(time.time())
    canvas = 1489154074
    arr1 = [
        64, 0, 1, 14,
        salt_payload[14], salt_payload[15],
        salt_form[14],    salt_form[15],
        salt_ua[14],      salt_ua[15],
        (ts >> 24) & 255, (ts >> 16) & 255, (ts >> 8) & 255, ts & 255,
        (canvas >> 24) & 255, (canvas >> 16) & 255, (canvas >> 8) & 255, canvas & 255,
        64,
    ]
    for i in range(1, 18):
        arr1[18] ^= arr1[i]
    return [arr1[0],arr1[2],arr1[4],arr1[6],arr1[8],arr1[10],arr1[12],arr1[14],arr1[16],arr1[18],
            arr1[1],arr1[3],arr1[5],arr1[7],arr1[9],arr1[11],arr1[13],arr1[15],arr1[17]]

def _get_xbogus(payload):
    short = "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe="
    arr2  = _get_arr2(payload, UA)
    tmp   = _rc4(['ÿ'], "".join(chr(i) for i in [2, 255] + arr2))
    garbled = [2, 255] + list(tmp)
    xb = ""
    for i in range(0, 21, 3):
        n = garbled[i] << 16 | garbled[i+1] << 8 | garbled[i+2]
        xb += short[(n>>18)&63] + short[(n>>12)&63] + short[(n>>6)&63] + short[n&63]
    return xb

def signed_url(base_url, payload):
    xb = _get_xbogus(payload)
    return base_url + payload + "&X-Bogus=" + xb

# ── HTTP 工具 ──────────────────────────────────────────────────────────────────

def get(url, timeout=15):
    r = requests.get(url, headers=DEFAULT_HEADER, timeout=timeout)
    r.raise_for_status()
    return r

# ── Cookie 有效性检测 ──────────────────────────────────────────────────────────

def check_login_status():
    """
    检测当前 Cookie 是否包含有效的登录态。
    抖音登录后 Cookie 中会有 sessionid / sid_tt / uid_tt 等字段。
    返回 (is_logged_in: bool, uid: str)
    """
    # 从 COOKIE 字符串中提取 sessionid 和 uid_tt
    session_match = re.search(r'sessionid=([^;]+)', COOKIE)
    uid_match     = re.search(r'uid_tt=([^;]+)', COOKIE)

    session_id = session_match.group(1).strip() if session_match else ''
    uid_tt     = uid_match.group(1).strip()     if uid_match     else ''

    # sessionid 存在且不是占位值（长度 >= 20），视为登录态
    is_logged_in = bool(session_id and len(session_id) >= 20 and uid_tt)
    return is_logged_in, uid_tt

# ── 文件存储 ───────────────────────────────────────────────────────────────────

def _url_md5(url):
    return hashlib.md5(url.encode()).hexdigest()

def _aweme_file(home_url):
    return _url_md5(home_url) + '-aweme.history'

def _profile_file(home_url):
    return _url_md5(home_url) + '-userprofile.history'

def load_history(home_url):
    path = _aweme_file(home_url)
    if not os.path.exists(path):
        return set()
    with open(path, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def save_history(home_url, aweme_id):
    with open(_aweme_file(home_url), 'a', encoding='utf-8') as f:
        f.write(aweme_id.strip() + '\n')

def load_profile(home_url):
    """返回 dict: {nickname, signature, ip_location}，文件不存在时返回空值"""
    path = _profile_file(home_url)
    result = {'nickname': '', 'signature': '', 'ip_location': ''}
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

def save_profile(home_url, nickname, signature, ip_location):
    path = _profile_file(home_url)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'nickname:{nickname}\nsignature:{signature}\nip_location:{ip_location}\n')

# ── 抖音 API ───────────────────────────────────────────────────────────────────

def get_sec_uid(home_url):
    """从短链/主页 URL 获取 sec_uid"""
    r = get(home_url)
    m = re.search(r'sec_uid=([^&]+)', r.url)
    if not m:
        raise ValueError(f"无法从重定向 URL 解析 sec_uid: {r.url}")
    return m.group(1)

def get_user_profile(sec_uid):
    """返回 (nickname, signature, ip_location)"""
    payload = f'sec_user_id={sec_uid}&{DEFAULT_PAYLOAD_SUFFIX}'
    url = signed_url(USER_PROFILE_URL, payload)
    r = get(url)
    data = r.json()
    user = data['user']
    return user['nickname'], user.get('signature', ''), user.get('ip_location', '')

def fetch_video_page(sec_uid, max_cursor):
    """获取一页视频，返回 (aweme_list, max_cursor, has_more)"""
    payload = f'sec_user_id={sec_uid}&max_cursor={max_cursor}&count=18&{DEFAULT_PAYLOAD_SUFFIX}'
    url = signed_url(USER_POST_URL, payload)
    r = get(url)
    data = r.json()
    aweme_list = data.get('aweme_list') or []
    return aweme_list, data.get('max_cursor', 0), bool(data.get('has_more', 0))

def fetch_all_videos(sec_uid):
    """
    翻页获取全部视频，返回所有 aweme item 列表。
    未登录时 API 通常只返回第一页且 has_more=0，此函数会如实返回。
    """
    all_items = []
    max_cursor = 0
    has_more = True
    attempts = 0

    while has_more and attempts < 50:  # 最多翻50页（约900条）
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

        # 避免请求过快
        if has_more:
            time.sleep(0.5)

    return all_items

def parse_video(item):
    """从 aweme item 提取关键字段"""
    ts = item['create_time']
    dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
    date_prefix = time.strftime('%Y-%m-%d', time.localtime(ts))
    raw_desc = item.get('desc', '') or ''
    safe_desc = re.sub(r'[\\/:*?"<>|]', '', raw_desc) or '无标题'
    # 文件名格式：[日期] 标题，方便排序和识别
    title = f'[{date_prefix}] {safe_desc}'
    # 优先选非 v26-web.douyinvod.com 的 CDN
    urls = item['video']['play_addr']['url_list']
    video_url = next((u for u in urls if 'v26-web.douyinvod.com' not in u), urls[0])
    cover_url = item['video']['cover']['url_list'][0]
    # 提取点赞数
    stats = item.get('statistics') or {}
    digg_count = stats.get('digg_count', 0)
    return {
        'aweme_id':    item['aweme_id'],
        'title':       title,
        'desc':        safe_desc,
        'create_time': dt,
        'date':        date_prefix,
        'url':         video_url,
        'cover_url':   cover_url,
        'digg_count':  digg_count,
    }

# ── 视频下载 ───────────────────────────────────────────────────────────────────

def download_video(video_url, dest_path):
    """下载视频到 dest_path（不含扩展名），返回实际文件路径"""
    url = video_url.replace('aweme.snssdk.com', 'api.amemv.com')
    mp4_path = dest_path + '.mp4'
    with closing(requests.get(url, headers=DEFAULT_HEADER, stream=True, timeout=60)) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        done = 0
        with open(mp4_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done / total * 100
                    sys.stderr.write(f'\r  下载进度: {pct:.1f}%')
        sys.stderr.write('\n')
    return mp4_path

# ── 事件输出 ───────────────────────────────────────────────────────────────────

def emit(event: dict):
    """将事件以 JSON Lines 格式输出到 stdout，供 SKILL.md 中的 Claude 解析"""
    print(json.dumps(event, ensure_ascii=False), flush=True)

# ── 首次初始化模式 ─────────────────────────────────────────────────────────────

def init_one(label, home_url, save_dir):
    """
    首次添加监控目标时调用：
    1. 检测登录态
    2. 获取用户资料
    3. 全量抓取所有视频列表（翻页到底）
    4. 下载所有视频到本地
    5. 写入历史记录（后续只通知增量）
    6. 输出 init_complete 事件
    """
    sys.stderr.write(f'[init] 开始初始化: {label} ({home_url})\n')

    # 1. 检测登录态
    is_logged_in, uid = check_login_status()
    if not is_logged_in:
        emit({
            'type': 'error',
            'code': 'cookie_invalid',
            'label': label,
            'message': (
                'Cookie 未配置或已失效，未登录状态下抖音 API 只返回部分数据。'
                '请更新 scripts/monitor.py 中的 COOKIE 变量后重试。'
                '获取方式：浏览器打开 https://www.douyin.com 登录 → F12 → Network → 任意请求 → Request Headers → 复制 cookie 值'
            )
        })
        # 未登录仍继续，但结果可能不完整
        sys.stderr.write('[init] 警告：Cookie 可能失效，继续尝试但结果可能不完整\n')

    # 2. 获取 sec_uid
    try:
        sec_uid = get_sec_uid(home_url)
    except Exception as e:
        emit({'type': 'error', 'code': 'sec_uid_failed', 'label': label, 'message': str(e)})
        return

    # 3. 获取用户资料
    try:
        nickname, signature, ip_location = get_user_profile(sec_uid)
    except Exception as e:
        emit({'type': 'error', 'code': 'profile_failed', 'label': label, 'message': str(e)})
        return

    save_profile(home_url, nickname, signature, ip_location)

    # 4. 全量抓取视频列表
    sys.stderr.write(f'[init] 开始全量抓取视频列表...\n')
    all_items = fetch_all_videos(sec_uid)
    total_count = len(all_items)
    sys.stderr.write(f'[init] 共获取到 {total_count} 条视频\n')

    # 5. 下载所有视频并写入历史
    user_dir = os.path.join(save_dir, nickname)
    os.makedirs(user_dir, exist_ok=True)

    downloaded = []
    failed = []

    # 从最早的视频开始下载（倒序，保证按时间顺序写历史）
    for item in reversed(all_items):
        v = parse_video(item)
        dest = os.path.join(user_dir, v['title'])
        mp4_path = dest + '.mp4'

        # 已存在则跳过下载
        if os.path.exists(mp4_path):
            sys.stderr.write(f'[init] 已存在，跳过: {v["title"]}\n')
            save_history(home_url, v['aweme_id'])
            downloaded.append({
                'title':       v['desc'],
                'create_time': v['create_time'],
                'date':        v['date'],
                'digg_count':  v['digg_count'],
                'cover_url':   v['cover_url'],
                'file_path':   mp4_path,
            })
            continue

        try:
            sys.stderr.write(f'[init] 下载: {v["title"]}\n')
            file_path = download_video(v['url'], dest)
            save_history(home_url, v['aweme_id'])
            downloaded.append({
                'title':       v['desc'],
                'create_time': v['create_time'],
                'date':        v['date'],
                'digg_count':  v['digg_count'],
                'cover_url':   v['cover_url'],
                'file_path':   file_path,
            })
        except Exception as e:
            sys.stderr.write(f'[init] 下载失败: {v["title"]} — {e}\n')
            # 下载失败也写入历史，避免重复下载
            save_history(home_url, v['aweme_id'])
            failed.append({
                'title':       v['desc'],
                'create_time': v['create_time'],
                'digg_count':  v['digg_count'],
                'cover_url':   v['cover_url'],
                'file_path':   '',
                'error':       str(e),
            })

    # video_list 按发布时间从新到旧排列，方便 SKILL.md 展示最近 10 条
    all_results = downloaded + failed
    all_results.sort(key=lambda x: x['create_time'], reverse=True)

    # 6. 输出 init_complete 事件
    emit({
        'type':           'init_complete',
        'label':          label,
        'nickname':       nickname,
        'signature':      signature,
        'ip_location':    ip_location,
        'save_dir':       user_dir,
        'total_videos':   total_count,
        'downloaded':     len(downloaded),
        'failed':         len(failed),
        'video_list':     all_results,  # 从新到旧，供 SKILL.md 展示最近10条并发送
        'login_warning':  not is_logged_in,
        'message': (
            f'{label}（{nickname}）初始化完成：'
            f'共 {total_count} 条视频，'
            f'下载成功 {len(downloaded)} 条，'
            f'失败 {len(failed)} 条。'
            f'保存路径：{user_dir}'
        )
    })

# ── 增量监控模式 ───────────────────────────────────────────────────────────────

def monitor_one(label, home_url, save_dir):
    """
    增量监控单个主页，只处理历史记录中没有的新视频。
    label: 用户自定义名称，如"刘德华"
    home_url: 抖音主页链接
    save_dir: 视频保存根目录
    """
    sys.stderr.write(f'[monitor] 开始处理: {label} ({home_url})\n')

    # 1. 获取 sec_uid
    try:
        sec_uid = get_sec_uid(home_url)
    except Exception as e:
        sys.stderr.write(f'[monitor] 获取 sec_uid 失败: {e}\n')
        return

    # 2. 获取并比较用户资料
    try:
        nickname, signature, ip_location = get_user_profile(sec_uid)
    except Exception as e:
        sys.stderr.write(f'[monitor] 获取用户资料失败: {e}\n')
        return

    old_profile = load_profile(home_url)
    if old_profile['nickname']:  # 有历史记录，才比较
        changes = []
        if old_profile['nickname'] != nickname:
            changes.append(f'昵称: {old_profile["nickname"]} → {nickname}')
        if old_profile['signature'] != signature:
            changes.append(f'签名: {old_profile["signature"]} → {signature}')
        if old_profile['ip_location'] != ip_location:
            changes.append(f'IP归属: {old_profile["ip_location"]} → {ip_location}')
        if changes:
            emit({
                'type':    'profile_update',
                'label':   label,
                'nickname': nickname,
                'changes': changes,
                'message': f'{label} 更新了主页信息：' + '；'.join(changes),
            })
    save_profile(home_url, nickname, signature, ip_location)

    # 3. 获取视频列表（增量：遇到全部已知则停止翻页）
    history = load_history(home_url)
    max_cursor = 0
    has_more = True
    new_videos = []
    attempts = 0

    while has_more and attempts < 15:
        attempts += 1
        try:
            items, max_cursor, has_more = fetch_video_page(sec_uid, max_cursor)
        except Exception as e:
            sys.stderr.write(f'[monitor] 获取视频页失败: {e}\n')
            break

        page_new = [parse_video(i) for i in items if parse_video(i)['aweme_id'] not in history]
        new_videos.extend(page_new)

        # 如果当前页所有视频都在历史中，不必继续翻页
        if items and all(parse_video(i)['aweme_id'] in history for i in items):
            break

    # 4. 下载新视频并发出通知
    if not new_videos:
        sys.stderr.write(f'[monitor] {label}: 无新视频\n')
        return

    user_dir = os.path.join(save_dir, nickname)
    os.makedirs(user_dir, exist_ok=True)

    # 倒序处理，让最早的视频先通知
    for v in reversed(new_videos):
        dest = os.path.join(user_dir, v['title'])
        try:
            sys.stderr.write(f'[monitor] 下载: {v["title"]}\n')
            file_path = download_video(v['url'], dest)
        except Exception as e:
            sys.stderr.write(f'[monitor] 下载失败: {e}\n')
            file_path = ''

        emit({
            'type':        'new_video',
            'label':       label,
            'nickname':    nickname,
            'aweme_id':    v['aweme_id'],
            'title':       v['desc'],
            'create_time': v['create_time'],
            'cover_url':   v['cover_url'],
            'video_url':   v['url'],
            'file_path':   file_path,
            'message':     f'{label} 发布了新视频：{v["desc"]}（{v["create_time"]}）',
        })
        save_history(home_url, v['aweme_id'])


def main():
    args = sys.argv[1:]

    if not args:
        sys.stderr.write(
            '用法:\n'
            '  # 增量监控\n'
            '  python monitor.py \'{"save_dir":"./Download","targets":[{"label":"xx","url":"https://v.douyin.com/xxx"}]}\'\n'
            '  # 首次初始化（全量抓取+下载）\n'
            '  python monitor.py --init \'{"save_dir":"./Download","targets":[{"label":"xx","url":"https://v.douyin.com/xxx"}]}\'\n'
        )
        sys.exit(1)

    init_mode = False
    if args[0] == '--init':
        init_mode = True
        args = args[1:]

    if not args:
        sys.stderr.write('错误：缺少 JSON 配置参数\n')
        sys.exit(1)

    config   = json.loads(args[0])
    save_dir = config.get('save_dir', './Download')
    targets  = config.get('targets', [])

    for t in targets:
        if init_mode:
            init_one(t['label'], t['url'], save_dir)
        else:
            monitor_one(t['label'], t['url'], save_dir)


if __name__ == '__main__':
    main()
