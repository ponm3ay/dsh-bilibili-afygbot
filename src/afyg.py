#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
椰果数据仓 · afyg.py
====================
把 B站 刷来的「凹分轴 / 出分」沉淀成结构化数据，并对外提供只读 HTTP API。

零第三方依赖（仅标准库），可脱离 DSH 单独运行。

子命令
------
  extract  <BV号>...           抓取并打印结构化记录（不落盘，便于核对）
  backfill <BV号>...           抓取并追加进 data/records.jsonl（自动去重）
  ingest   <file.json>         外部 JSON（数组或单条）校验后入库
  list     [--kind --team ...] 终端查看
  get      <id>                看单条
  stats                        统计
  validate                     全量校验
  export   --format afyg       导出成椰果工坊「工程」映射（干跑，只打印）
  serve    [--port 8787]       起 HTTP API

数据
----
  data/records.jsonl           append-only，每行一条
  data/schema.json             JSON Schema：dsh.wuwa/afyg-record@1
"""
import argparse, json, os, re, subprocess, sys, threading, time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HOME = os.path.dirname(os.path.abspath(__file__))      # <repo>/src
ROOT = os.path.dirname(HOME)                            # <repo>
# 数据目录：可用 AFYG_DATA 覆盖（默认 <repo>/data）
DATA = os.environ.get('AFYG_DATA') or os.path.join(ROOT, 'data')
RECORDS = os.path.join(DATA, 'records.jsonl')
SCHEMA_FILE = os.environ.get('AFYG_SCHEMA') or os.path.join(ROOT, 'schema', 'afyg-record.v1.json')
CN = timezone(timedelta(hours=8))
SCHEMA_ID = 'dsh.wuwa/afyg-record@1'
KINDS = ('rotation', 'score')
TIERS = ('wheelchair', 'advanced', 'peak')
UNITS = ('score', 'dps', 'seconds')
MODES = ('matrix', 'toa', 'other')
WHERE = ('comment', 'description', 'subtitle', 'onscreen', 'pinned', 'video')
# 抓取用的 MCP 工具箱（需自己准备 mcp_server.py，见 patches/README）
MCP_SCRIPT = os.environ.get('AFYG_MCP') or os.path.join(ROOT, 'src', 'mcp_server.py')
# 跑 MCP 的 Python：优先用 AFYG_PYTHON，其次本机 venv，最后当前解释器
PY_EXE = os.environ.get('AFYG_PYTHON') or ''
if not PY_EXE:
    for _cand in (os.path.join(ROOT, '.venv', 'Scripts', 'python.exe'),
                  os.path.join(ROOT, '.venv', 'bin', 'python')):
        if os.path.exists(_cand):
            PY_EXE = _cand
            break
if not PY_EXE:
    PY_EXE = sys.executable


def now_iso():
    return datetime.now(CN).isoformat(timespec='seconds')


def ensure_dirs():
    os.makedirs(DATA, exist_ok=True)


# ─────────────────────────── 记录 ID / 校验 ───────────────────────────

def make_id(rec):
    bv = str(rec.get('source', {}).get('bvid', '')).strip()
    kinds = '+'.join(sorted(rec.get('kinds') or []))
    return 'r_%s_%s' % (bv, kinds.replace('+', '-') or 'x')


def validate(rec):
    """返回错误列表；空列表＝通过。"""
    e = []
    if not isinstance(rec, dict):
        return ['record must be an object']
    if rec.get('schema') != SCHEMA_ID:
        e.append('schema must be %r' % SCHEMA_ID)
    for k in ('kinds', 'source', 'capturedAt', 'capturedBy'):
        if not rec.get(k):
            e.append('missing %s' % k)
    src = rec.get('source') or {}
    if not src.get('bvid'):
        e.append('missing source.bvid')
    if not src.get('url'):
        e.append('missing source.url')
    up = src.get('up') or {}
    if not up.get('homepage'):
        e.append('missing source.up.homepage  ← 硬要求：UP 主页链接')
    for k in rec.get('kinds') or []:
        if k not in KINDS:
            e.append('unknown kind %r' % k)
    sc = rec.get('score') or {}
    if sc.get('tier') and sc['tier'] not in TIERS:
        e.append('unknown tier %r' % sc['tier'])
    if sc.get('unit') and sc['unit'] not in UNITS:
        e.append('unknown unit %r' % sc['unit'])
    if sc.get('mode') and sc['mode'] not in MODES:
        e.append('unknown mode %r' % sc['mode'])
    rot = rec.get('rotation') or {}
    if rot.get('where') and rot['where'] not in WHERE:
        e.append('unknown rotation.where %r' % rot['where'])
    if rot.get('hasText') and not rot.get('text'):
        e.append('rotation.hasText=true 但没有 rotation.text')
    return e


def normalize(rec):
    """补默认值、算 id、清理空字段。"""
    rec = dict(rec)
    rec.setdefault('schema', SCHEMA_ID)
    rec.setdefault('kinds', [])
    rec.setdefault('tags', [])
    rec.setdefault('capturedAt', now_iso())
    rec.setdefault('capturedBy', 'dsh-bili-scroll/0.1.2')
    src = dict(rec.get('source') or {})
    up = dict(src.get('up') or {})
    if up.get('mid') and not up.get('homepage'):
        up['homepage'] = 'https://space.bilibili.com/%s' % up['mid']
    src['up'] = up
    rec['source'] = src
    rec['id'] = rec.get('id') or make_id(rec)
    return rec


# ─────────────────────────── 存储 ───────────────────────────

def read_all():
    if not os.path.exists(RECORDS):
        return []
    out = []
    with open(RECORDS, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def append(recs):
    ensure_dirs()
    existing = {r.get('id') for r in read_all()}
    added, skipped = [], []
    with open(RECORDS, 'a', encoding='utf-8', newline='\n') as f:
        for r in recs:
            r = normalize(r)
            errs = validate(r)
            if errs:
                skipped.append((r.get('id'), errs))
                continue
            if r['id'] in existing:
                skipped.append((r['id'], ['duplicate']))
                continue
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            existing.add(r['id'])
            added.append(r['id'])
    return added, skipped


# ─────────────────────────── MCP 抓取 ───────────────────────────

class Mcp:
    def __init__(self, script, py_exe=None):
        self.proc = subprocess.Popen(
            [py_exe or PY_EXE, script],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self._id = 0
        self._send({'jsonrpc': '2.0', 'id': self._next(),
                    'method': 'initialize',
                    'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                               'clientInfo': {'name': 'afyg', 'version': '1'}}})
        time.sleep(0.8)
        self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        time.sleep(0.2)

    def _next(self):
        self._id += 1
        return self._id

    def _send(self, obj):
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + chr(10)).encode('utf-8'))
        self.proc.stdin.flush()

    def call(self, name, args, timeout=40):
        rid = self._next()
        self._send({'jsonrpc': '2.0', 'id': rid, 'method': 'tools/call',
                    'params': {'name': name, 'arguments': args}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                return None
            try:
                d = json.loads(line.decode('utf-8', 'replace'))
            except Exception:
                continue
            if d.get('id') != rid:
                continue
            c = (d.get('result') or {}).get('content') or []
            if not c:
                return None
            try:
                return json.loads(c[0]['text'])
            except Exception:
                return c[0].get('text')
        return None

    def close(self):
        try:
            self.proc.kill()
        except Exception:
            pass


# ─────────────────────────── 标题解析 ───────────────────────────

# 手法记号串：4R17居 / 5R10E9处决 / 5z21居 / 6R24死告 / 5R20Z ...
NOTATION_RE = re.compile(r'\d+\s*[Rr]\s*\d*\s*(?:[Ee]\s*\d+)?\s*(?:[\u4e00-\u9fff]{1,2}|\d+[Zz])?')
SCORE_RE = re.compile(r'(\d{4,6})\s*分')
WAN_RE = re.compile(r'(\d+(?:\.\d+)?)\s*[wW]\b|(\d+(?:\.\d+)?)\s*万')
DPS_RE = re.compile(r'(\d+(?:\.\d+)?)\s*[wW]?\s*(?:wdps|dps|DPS)')
SEC_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:秒|s|S)\b')
TEAM_RE = re.compile(r'[\u4e00-\u9fff]{3}')
CHAIN_RE = re.compile(r'\b(0?1|1|2|3|4|5|6)\s*链?')

SEASON_RE = re.compile(r'[Ss]\s*(\d)\s*[-.\s]?\s*(\d)?')
# 「文字轴」是圈内正式说法；「蚊子轴 / 蚊子粥」是同音黑话，都算
ROT_HINT = ('文字轴', '蚊子轴', '蚊子粥', '轴如下', '轴：', '轴:', '循环轴', '启动轴',
            '手法', '流程如下', '延奏', '变奏', '处决', '居合', '合轴')


def guess_kinds(title, desc, has_rotation):
    kinds = []
    if has_rotation or any(w in (title or '') + (desc or '') for w in
                           ('教学', '轴', '手法', '循环', '演示', '流程', '进阶', '神轴')):
        kinds.append('rotation')
    if SCORE_RE.search(title or '') or WAN_RE.search(title or '') or DPS_RE.search(title or '') \
       or '分' in (title or '') or '凹分' in (desc or ''):
        kinds.append('score')
    return kinds or ['score']


# 配队缩写：三个汉字 + 紧跟手法记号或分数（绯洛穗4R17居 / 露丽莫106593分 / 景月露25s）
# 配队词表：只认已知的三字队名。认不出就留空 —— 宁缺毋滥，别把「美流程」当队名。
# 这张表随入库记录沉淀；也可由使用者在 data/teams.txt 里追加（一行一个）。
TEAM_VOCAB = [
    '绯洛穗', '爱达千', '清达莫', '露丽莫', '景月露', '心雷穗', '爱琳莫', '龙凤守',
    '景月莫', '西仇守', '日月守', '秧千穗', '心千穗', '卡夏千', '赞菲守', '心卜穗',
    '丹莫维', '弗坎莫', '露丽维', '月琳维', '景日莫', '景莫守', '锁琳莫', '洛莫守',
    '心雷卜', '卡光守', '爱达穗', '绯琳莫', '秧丽穗', '嘉斐维', '今心守', '心汐守',
    '卡夏风', '散西守', '秧千穗', '景月守', '赞菲光', '洛琳守', '锁洛守',
]


def team_vocab():
    """内置词表 + 用户可编辑的 data/teams.txt（一行一个）。"""
    extra = []
    f = os.path.join(DATA, 'teams.txt')
    if os.path.exists(f):
        try:
            extra = [l.strip() for l in open(f, encoding='utf-8') if l.strip() and not l.startswith('#')]
        except Exception:
            extra = []
    return list(dict.fromkeys(TEAM_VOCAB + extra))


def parse_team(title, desc=''):
    """在标题/简介里找已知队名。长名优先（避免「爱达千」压过「爱达千穗」）。"""
    blob = (title or '') + ' ' + (desc or '')
    for abbr in sorted(team_vocab(), key=len, reverse=True):
        if abbr in blob:
            return {'abbr': abbr, 'members': [], 'slots': []}
    return None


def parse_notation(title):
    m = NOTATION_RE.search(title or '')
    return m.group(0).strip() if m else None


def parse_score(title, desc=''):
    t = title or ''
    m = SCORE_RE.search(t)
    if m:
        # raw 只留数字：有没有「分」字都算分，别把后缀带进数据库
        return {'value': int(m.group(1)), 'unit': 'score', 'raw': str(int(m.group(1)))}
    # 裸数字兜底：5~6 位、独立成词（如 "58444无宝箱" "96386"），当作分数
    m = re.search(r'(?<![\d.])(\d{5,6})(?![\d.])', t)
    if m:
        return {'value': int(m.group(1)), 'unit': 'score', 'raw': str(int(m.group(1)))}
    m = DPS_RE.search(t)
    if m:
        v = float(m.group(1))
        if 'w' in t.lower()[:m.end()].split()[-1:][0] if t.lower()[:m.end()].split() else False:
            v *= 10000
        return {'value': int(v), 'unit': 'dps', 'raw': m.group(0).strip()}
    m = WAN_RE.search(t)
    if m:
        v = float(m.group(1) or m.group(2)) * 10000
        return {'value': int(v), 'unit': 'score', 'raw': m.group(0).strip()}
    return None


def parse_season(title, desc=''):
    m = SEASON_RE.search(title or '')
    if m:
        return 'S%s%s' % (m.group(1), ('-' + m.group(2)) if m.group(2) else '')
    return None


def tier_of(title, desc='', score=None):
    blob = (title or '') + ' ' + (desc or '')
    low = ('轮椅', '萌新', '手残', '无脑', '放空大脑', '一键', '挂机', '保姆级', '入门', '0合轴', '简易', '简化')
    peak = ('巅峰', '极限', '顶分', '国服', '手搓', '满合轴', '神轴')
    if any(w in blob for w in low):
        return 'wheelchair'
    if any(w in blob for w in peak):
        return 'peak'
    if score and score.get('value', 0) >= 90000:
        return 'peak'
    return 'advanced'


ROT_KW = ('轴', '变奏', '延奏', '处决', '合轴', '循环', '启动', '手法', '流程', '强变', '协奏')


def rot_score(s):
    """给一段文字打「像不像文子轴」的分。

    圈内记谱长这样：月EQ闪 露RE 月跳闪E 露aaa 阳ZEaaa阴Z 处决aaa阴Z
    —— 特征是中文字 + 紧贴的大写字母串混排，而不是 a1234 这种数字记法。
    """
    hits = sum(3 for w in ROT_KW if w in s)
    marks = len(re.findall(r'[\u4e00-\u9fff][A-Za-z]{1,4}', s))       # 月EQ / 露RE / 阳ZE
    marks += len(re.findall(r'(?<![A-Za-z])(?:aaa|aa|a{2,})(?![A-Za-z])', s))  # aaa 平A串
    marks += len(re.findall(r'[（(]变奏[)）]', s))                     # （变奏）
    return hits + min(marks, 14)


# 看着像「聊天/观点」的，不可能是记谱
CHITCHAT = ('大月卡', '关注我', '谢谢', '私信', '加群', '我觉得', '感觉', '其实',
            '不如', '大家', '萌新', '萌新求', '哈哈哈', '笑死')


def find_rotation(strings):
    """从候选文本里挑最像「文字轴」的。

    判据（2026-10-19 收紧过一次）：**必须有 ≥6 个「中文字+字母」粘连的记号**。
    真实记谱是「月EQ闪 露RE 月跳闪E 露aaa 阳ZEaaa阴Z」这种密排；
    而「有几把尾轮处决不出来…」这类聊天虽然含"处决"，粘连记号≈0 —— 会被正确排除。
    """
    best = None
    for s in strings:
        if not isinstance(s, str) or len(s) < 40:
            continue
        if any(w in s for w in CHITCHAT):
            continue
        marks = len(re.findall(r'[\u4e00-\u9fff][A-Za-z]{1,4}', s))
        marks += len(re.findall(r'(?<![A-Za-z])(?:aaa|a{2,})(?![A-Za-z])', s))
        marks += len(re.findall(r'[（(]变奏[)）]', s))
        if marks < 6:
            continue
        sc = rot_score(s)
        if sc >= 8 and (best is None or sc > best[0]):
            best = (sc, s.strip())
    return best[1] if best else None


def rot_tokens(text):
    """抽出可检索的记号（给别的 agent 做索引/比对用）。"""
    if not text:
        return []
    toks = re.findall(r'[\u4e00-\u9fff]?[A-Za-z]{2,5}[\u4e00-\u9fff]?', text)
    return list(dict.fromkeys(t.strip() for t in toks if len(t.strip()) >= 2))[:40]


def walk_strings(obj, out=None, depth=0):
    if out is None:
        out = []
    if depth > 6:
        return out
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            walk_strings(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            walk_strings(v, out, depth + 1)
    return out


def extract_one(mcp, bvid, fetch_comments=True):
    info = mcp.call('bili_video_info', {'bvid': bvid})
    if not isinstance(info, dict):
        print('  ! %s 取不到 info' % bvid, file=sys.stderr)
        return None
    title = info.get('title') or ''
    desc = info.get('description') or ''
    up = info.get('up') or {}
    if not up.get('homepage') and up.get('mid'):
        up['homepage'] = 'https://space.bilibili.com/%s' % up['mid']

    rot_text, rot_where, rot_evidence = None, None, None
    if any(w in desc for w in ROT_HINT) and len(desc) > 30:
        cand = find_rotation([desc])
        if cand:
            rot_text, rot_where, rot_evidence = cand, 'description', 'https://www.bilibili.com/video/%s' % bvid

    if not rot_text and fetch_comments:
        cm = mcp.call('bili_comments', {'bvid': bvid, 'num': 30})
        if cm:
            cand = find_rotation(walk_strings(cm))
            if cand:
                rot_text, rot_where = cand, 'comment'
                rot_evidence = 'https://www.bilibili.com/video/%s' % bvid

    score = parse_score(title, desc)
    team = parse_team(title, desc)
    kinds = guess_kinds(title, desc, bool(rot_text))
    tier = tier_of(title, desc, score)
    stat = info.get('stat') or {}

    rec = {
        'schema': SCHEMA_ID,
        'kinds': kinds,
        'source': {
            'platform': 'bilibili',
            'bvid': bvid,
            'url': 'https://www.bilibili.com/video/%s' % bvid,
            'title': title,
            'publishedAt': info.get('published'),
            'ageDays': info.get('age_days'),
            'up': {'name': up.get('name'), 'mid': up.get('mid'), 'homepage': up.get('homepage')},
            'stats': {'view': stat.get('view', 0), 'reply': stat.get('reply', 0),
                      'like': stat.get('like', 0)},
        },
        'rotation': {
            'hasText': bool(rot_text),
            'text': rot_text,
            'format': 'notation' if rot_text and re.search(r'[a-zA-Z]\d', rot_text) else 'freeform',
            'where': rot_where,
            'evidenceUrl': rot_evidence,
            'tokens': rot_tokens(rot_text),
        } if rot_text or 'rotation' in kinds else None,
        'score': dict(score, mode='matrix', season=parse_season(title, desc), tier=tier)
                 if score else {'tier': tier, 'mode': 'matrix', 'season': parse_season(title, desc)},
        'team': team,
        'tags': [t for t in [parse_season(title, desc), '矩阵' if '矩阵' in title + desc else None] if t],
        'capturedAt': now_iso(),
        'capturedBy': 'dsh-bili-scroll/0.1.2(+afyg.py)',
        'confidence': 0.75 if rot_text else 0.6,
        'notes': '由 afyg.py 自动抽取；拿不准的字段留空，别猜。',
    }
    if not rec.get('rotation'):
        rec.pop('rotation', None)
    return normalize(rec)


# ─────────────────────────── 查询 ───────────────────────────

def query(kind=None, team=None, tier=None, mode=None, season=None, q=None,
          since=None, limit=100, offset=0, sort='new'):
    rows = read_all()
    def keep(r):
        if kind and kind not in (r.get('kinds') or []):
            return False
        if team:
            t = (r.get('team') or {}).get('abbr') or ''
            if team.lower() not in t.lower():
                return False
        sc = r.get('score') or {}
        if tier and sc.get('tier') != tier:
            return False
        if mode and sc.get('mode') != mode:
            return False
        if season and (sc.get('season') or '') != season:
            return False
        if since:
            p = (r.get('source') or {}).get('publishedAt') or ''
            if p < since:
                return False
        if q:
            blob = json.dumps(r, ensure_ascii=False).lower()
            if q.lower() not in blob:
                return False
        return True
    rows = [r for r in rows if keep(r)]
    if sort == 'score':
        rows.sort(key=lambda r: (r.get('score') or {}).get('value') or 0, reverse=True)
    else:
        rows.sort(key=lambda r: (r.get('source') or {}).get('publishedAt') or '', reverse=True)
    total = len(rows)
    return rows[offset:offset + limit], total


def stats():
    rows = read_all()
    def cnt(f):
        d = {}
        for r in rows:
            k = f(r)
            if k is None:
                continue
            d[k] = d.get(k, 0) + 1
        return dict(sorted(d.items(), key=lambda x: -x[1]))
    return {
        'total': len(rows),
        'kinds': cnt(lambda r: None if not r.get('kinds') else '+'.join(sorted(r['kinds']))),
        'tiers': cnt(lambda r: (r.get('score') or {}).get('tier')),
        'withRotationText': sum(1 for r in rows if (r.get('rotation') or {}).get('hasText')),
        'withUpHomepage': sum(1 for r in rows
                              if ((r.get('source') or {}).get('up') or {}).get('homepage')),
        'teams': cnt(lambda r: (r.get('team') or {}).get('abbr')),
        'generatedAt': now_iso(),
    }


def export_afyg(rec):
    """把一条记录映射成椰果工坊「工程」形状（干跑，不发布）。

    ⚠️ 预留位：真正的上传需要工坊的 POST /api/public/projects 与作者授权，
       这里只产出可被工具箱导入的骨架，字段不足时留 null 而不是编造。
    """
    src = rec.get('source') or {}
    team = rec.get('team') or {}
    slots = []
    for name in (team.get('slots') or []):
        slots.append({'character': name.get('character'), 'chain': name.get('chain'),
                      'weapon': name.get('weapon'), 'refinement': name.get('refinement')})
    return {
        'schema': 'dsh.wuwa/afyg-project-draft@1',
        'note': '干跑产物：字段缺失处为 null，未调用工坊写接口。',
        'title': (team.get('abbr') or '') + ' · ' + ((rec.get('score') or {}).get('raw') or src.get('title', '')),
        'authorName': None,
        'tags': rec.get('tags') or [],
        'teamPreview': {'names': team.get('members') or [], 'slots': slots},
        'rotationText': (rec.get('rotation') or {}).get('text'),
        'score': rec.get('score'),
        'provenance': {'platform': 'bilibili', 'bvid': src.get('bvid'),
                       'url': src.get('url'), 'up': (src.get('up') or {}).get('homepage')},
        'publish': None,
    }


# ─────────────────────────── HTTP API ───────────────────────────

API_DOC = {
    'schema': SCHEMA_ID,
    'base': '/v1',
    'auth': '只读接口无需鉴权；写接口预留，当前返回 501。',
    'endpoints': [
        {'method': 'GET', 'path': '/v1/health', 'desc': '存活检查'},
        {'method': 'GET', 'path': '/v1/schema', 'desc': 'JSON Schema'},
        {'method': 'GET', 'path': '/v1/stats', 'desc': '聚合统计'},
        {'method': 'GET', 'path': '/v1/records',
         'query': 'kind,team,tier,mode,season,q,since,limit,offset,sort(new|score)',
         'desc': '记录列表（分页）'},
        {'method': 'GET', 'path': '/v1/records/{id}', 'desc': '单条记录'},
        {'method': 'GET', 'path': '/v1/teams', 'desc': '配队聚合'},
        {'method': 'GET', 'path': '/v1/teams/{abbr}', 'desc': '某配队的全部记录'},
        {'method': 'GET', 'path': '/v1/ups', 'desc': 'UP 聚合'},
        {'method': 'GET', 'path': '/v1/ups/{mid}', 'desc': '某 UP 的全部记录'},
        {'method': 'GET', 'path': '/v1/export?format=jsonl|afyg', 'desc': '整库导出'},
        {'method': 'POST', 'path': '/v1/records', 'reserved': True,
         'desc': '外部写入（预留）：需鉴权，当前 501'},
        {'method': 'POST', 'path': '/v1/export/afyg', 'reserved': True,
         'desc': '一键登分/上传轴到椰果工坊（预留）：当前 501'},
    ],
}


def make_handler():
    class H(BaseHTTPRequestHandler):
        server_version = 'afyg/1'

        def log_message(self, *a):
            pass

        def _send(self, code, obj, ctype='application/json; charset=utf-8', raw=None):
            body = raw if raw is not None else json.dumps(obj, ensure_ascii=False, indent=2)
            data = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type,Authorization')
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._send(204, None, raw='')

        def do_POST(self):
            u = urlparse(self.path)
            self._send(501, {'error': 'reserved',
                             'message': '写接口为预留位，尚未启用（设计见 /v1/openapi）',
                             'path': u.path})

        def do_GET(self):
            u = urlparse(self.path)
            p, qs = u.path.rstrip('/') or '/', parse_qs(u.query)
            one = lambda k, d=None: (qs.get(k, [d])[0])

            if p in ('/', '/v1', '/v1/openapi'):
                return self._send(200, API_DOC)
            if p == '/v1/health':
                return self._send(200, {'ok': True, 'records': len(read_all()), 'time': now_iso()})
            if p == '/v1/schema':
                if os.path.exists(SCHEMA_FILE):
                    return self._send(200, json.load(open(SCHEMA_FILE, encoding='utf-8')))
                return self._send(404, {'error': 'schema not found'})
            if p == '/v1/stats':
                return self._send(200, stats())
            if p == '/v1/records':
                rows, total = query(kind=one('kind'), team=one('team'), tier=one('tier'),
                                    mode=one('mode'), season=one('season'), q=one('q'),
                                    since=one('since'), limit=int(one('limit', '50') or 50),
                                    offset=int(one('offset', '0') or 0), sort=one('sort', 'new'))
                return self._send(200, {'total': total, 'count': len(rows), 'records': rows})
            if p.startswith('/v1/records/'):
                rid = p.split('/', 3)[3]
                for r in read_all():
                    if r.get('id') == rid:
                        return self._send(200, r)
                return self._send(404, {'error': 'not found', 'id': rid})
            if p == '/v1/teams':
                agg = {}
                for r in read_all():
                    t = (r.get('team') or {}).get('abbr')
                    if not t:
                        continue
                    a = agg.setdefault(t, {'abbr': t, 'count': 0, 'members': (r.get('team') or {}).get('members')})
                    a['count'] += 1
                return self._send(200, {'total': len(agg),
                                        'teams': sorted(agg.values(), key=lambda x: -x['count'])})
            if p.startswith('/v1/teams/'):
                abbr = p.split('/', 3)[3]
                rows = [r for r in read_all() if (r.get('team') or {}).get('abbr') == abbr]
                return self._send(200, {'team': abbr, 'count': len(rows), 'records': rows})
            if p == '/v1/ups':
                agg = {}
                for r in read_all():
                    up = (r.get('source') or {}).get('up') or {}
                    mid = up.get('mid')
                    if not mid:
                        continue
                    a = agg.setdefault(str(mid), {'mid': mid, 'name': up.get('name'),
                                                  'homepage': up.get('homepage'), 'count': 0})
                    a['count'] += 1
                return self._send(200, {'total': len(agg),
                                        'ups': sorted(agg.values(), key=lambda x: -x['count'])})
            if p.startswith('/v1/ups/'):
                mid = p.split('/', 3)[3]
                rows = [r for r in read_all()
                        if str(((r.get('source') or {}).get('up') or {}).get('mid')) == mid]
                return self._send(200, {'mid': mid, 'count': len(rows), 'records': rows})
            if p == '/v1/export':
                fmt = one('format', 'jsonl')
                rows = read_all()
                if fmt == 'afyg':
                    return self._send(200, {'count': len(rows),
                                            'projects': [export_afyg(r) for r in rows]})
                return self._send(200, None, ctype='application/x-ndjson; charset=utf-8',
                                  raw=''.join(json.dumps(r, ensure_ascii=False) + chr(10) for r in rows))
            return self._send(404, {'error': 'unknown path', 'path': p,
                                    'hint': 'GET /v1/openapi 看接口清单'})

    return H


def serve(port=8787):
    ensure_dirs()
    srv = ThreadingHTTPServer(('127.0.0.1', port), make_handler())
    print('afyg API on http://127.0.0.1:%d/v1  (Ctrl-C 停)' % port)
    print('  GET /v1/openapi  接口清单     GET /v1/records  记录列表')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('bye')


# ─────────────────────────── CLI ───────────────────────────

def main():
    ap = argparse.ArgumentParser(description='椰果数据仓')
    sub = ap.add_subparsers(dest='cmd')

    sp = sub.add_parser('extract'); sp.add_argument('bvid', nargs='+')
    sp = sub.add_parser('backfill'); sp.add_argument('bvid', nargs='+')
    sp = sub.add_parser('ingest'); sp.add_argument('file')
    sp = sub.add_parser('list')
    sp.add_argument('--kind'); sp.add_argument('--team'); sp.add_argument('--tier')
    sp.add_argument('--q'); sp.add_argument('--limit', type=int, default=20)
    sp = sub.add_parser('get'); sp.add_argument('id')
    sub.add_parser('stats')
    sub.add_parser('validate')
    sp = sub.add_parser('export'); sp.add_argument('--format', default='afyg')
    sp = sub.add_parser('serve'); sp.add_argument('--port', type=int, default=8787)

    a = ap.parse_args()
    ensure_dirs()

    if a.cmd in ('extract', 'backfill'):
        if not os.path.exists(MCP_SCRIPT):
            sys.exit('找不到 MCP 工具箱：%s\n先按 patches/README.md 准备 mcp_server.py，或用 AFYG_MCP 指向它。' % MCP_SCRIPT)
        mcp = Mcp(MCP_SCRIPT)
        recs = []
        try:
            for bv in a.bvid:
                print('· 抓 %s' % bv)
                r = extract_one(mcp, bv)
                if r:
                    recs.append(r)
        finally:
            mcp.close()
        if a.cmd == 'extract':
            print(json.dumps(recs, ensure_ascii=False, indent=2))
        else:
            added, skipped = append(recs)
            print('入库 %d 条：%s' % (len(added), ', '.join(added) or '-'))
            for i, e in skipped:
                print('  跳过 %s: %s' % (i, '; '.join(e)))
    elif a.cmd == 'ingest':
        # 同时接受 JSON（对象/数组）与 JSONL（一行一条）
        text = open(a.file, encoding='utf-8').read().strip()
        try:
            raw = json.loads(text)
            recs = raw if isinstance(raw, list) else [raw]
        except json.JSONDecodeError:
            recs = [json.loads(l) for l in text.splitlines() if l.strip()]
        added, skipped = append(recs)
        print('入库 %d 条，跳过 %d 条' % (len(added), len(skipped)))
        for i, e in skipped:
            print('  跳过 %s: %s' % (i, '; '.join(e)))
    elif a.cmd == 'list':
        rows, total = query(kind=a.kind, team=a.team, tier=a.tier, q=a.q, limit=a.limit)
        print('共 %d 条，显示 %d 条' % (total, len(rows)))
        for r in rows:
            sc = r.get('score') or {}
            rot = r.get('rotation') or {}
            print('  [%s] %s %s %s%s' % (
                sc.get('tier') or '-', (r.get('team') or {}).get('abbr') or '-',
                sc.get('raw') or '-', '轴 ' if rot.get('hasText') else '', r.get('id')))
    elif a.cmd == 'get':
        for r in read_all():
            if r.get('id') == a.id:
                print(json.dumps(r, ensure_ascii=False, indent=2)); return
        print('没找到', a.id); sys.exit(1)
    elif a.cmd == 'stats':
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    elif a.cmd == 'validate':
        bad = 0
        for r in read_all():
            e = validate(r)
            if e:
                bad += 1
                print('✗ %s: %s' % (r.get('id'), '; '.join(e)))
        print('校验完成：%d 条，问题 %d 条' % (len(read_all()), bad))
        sys.exit(1 if bad else 0)
    elif a.cmd == 'export':
        rows = read_all()
        if a.format == 'afyg':
            print(json.dumps({'count': len(rows), 'projects': [export_afyg(r) for r in rows]},
                             ensure_ascii=False, indent=2))
        else:
            for r in rows:
                print(json.dumps(r, ensure_ascii=False))
    elif a.cmd == 'serve':
        serve(a.port)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
