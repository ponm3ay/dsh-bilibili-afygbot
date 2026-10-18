# 接进 `dsh-bili-scroll`

本项目**不修改**插件的核心运行逻辑（调度、互斥、流程都不动），只做两件事：

1. 给 MCP 工具箱**补字段**（发布时间、UP 主页）
2. 加**数据层 + HTTP 路由**

---

## 0. 先把工具补上

插件自带的 `mcp_server.py` 有两个缺口：

| 缺什么 | 后果 |
|---|---|
| 搜索/详情不返回**发布时间** | 时效规则（只收近 5 天）没法执行 |
| 详情不返回 **UP mid** | 拿不到 UP 主页，记录无法回源 |

修法见本文件末尾的 [补丁代码](#补丁代码)。

> ⚠️ **关键坑：改家目录会被覆盖**
>
> `lib/state.mjs` 的 `ensureHomeFiles()` 对这几个文件是 `overwrite = true`：
>
> ```js
> [join(pluginDir, 'vendor', 'bilibili-mcp', 'mcp_server.py'), join(stateDir, 'mcp_server.py'), true],
> [join(pluginDir, 'lib', 'asr.py'), join(stateDir, 'asr.py'), true],
> [join(pluginDir, 'prompts', 'duty.md'), join(stateDir, 'duty.md'), false],   // 这个不覆盖
> ```
>
> 也就是说：**改 $DSH_HOME/bili-duty/mcp_server.py 是白改** —— 插件下次加载会用 vendor 那份盖掉。
> **必须改 `node_modules/dsh-bili-scroll/vendor/bilibili-mcp/mcp_server.py`。**
>
> 反过来，`duty.md` 是 `false`，所以**章程可以直接改家目录那份**。

---

## 1. 装数据层

把 `src/data.mjs` 拷进插件的 `lib/`：

```bash
cp src/data.mjs <profile>/node_modules/dsh-bili-scroll/lib/data.mjs
```

## 2. 挂路由

在 `index.js` 顶部 import：

```js
import { SCHEMA, SCHEMA_ID, OPENAPI, readAll as dataReadAll, append as dataAppend,
         query as dataQuery, stats as dataStats, exportAfyg, instanceId } from './lib/data.mjs'
```

在 `handle()` 里、404 之前插入：

```js
/* ── 数据接口（v1）── */
if (path === '/api/bili-duty/v1' || path === '/api/bili-duty/v1/') {
  return sendJson(res, 200, { ...OPENAPI, instance: instanceId(stateDir) })
}

const dataJson = (code, obj, raw, ctype) => {
  const body = raw != null ? raw : JSON.stringify(obj)
  res.writeHead(code, {
    'content-type': ctype || 'application/json; charset=utf-8',
    'access-control-allow-origin': '*',
    'cache-control': 'no-store',
  })
  res.end(body)
}

if (path.startsWith('/api/bili-duty/v1')) {
  const sub = path.slice('/api/bili-duty/v1'.length).replace(/^\/+/, '')
  if (req.method === 'POST') {
    return dataJson(501, { error: 'reserved', message: '写接口为预留位' })
  }
  if (sub === 'health') return dataJson(200, {
    ok: true, records: dataReadAll(stateDir).length, instance: instanceId(stateDir),
  })
  if (sub === 'schema') return dataJson(200, SCHEMA)
  if (sub === 'stats')  return dataJson(200, dataStats(stateDir))
  if (sub === 'records') {
    const p2 = url.searchParams
    return dataJson(200, dataQuery(stateDir, {
      kind: p2.get('kind') || undefined, team: p2.get('team') || undefined,
      tier: p2.get('tier') || undefined, q: p2.get('q') || undefined,
      sort: p2.get('sort') || 'new',
      limit: p2.get('limit') || 50, offset: p2.get('offset') || 0,
    }))
  }
  return dataJson(404, { error: 'unknown data path' })
}
```

> 完整实现见插件里的 `data.mjs` 与 `index.js`（含 teams / ups / export / records/:id）。

## 3. 让每轮写数据

在章程（`duty.md`）里加一段，要求每轮把挑中的视频**追加一行 JSON** 到
`data/records.jsonl`。示例见 [`charter/duty.zh-CN.md`](../charter/duty.zh-CN.md) 的「数据落库」一节。

---

## 补丁代码

### 时间辅助函数（放在 `mcp = FastMCP(...)` 之后）

```python
from datetime import datetime, timezone, timedelta

CN_TZ = timezone(timedelta(hours=8))

def _fmt_ts(ts) -> str:
    try:
        ts = int(ts or 0)
        if ts <= 0:
            return ""
        return datetime.fromtimestamp(ts, CN_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""

def _age_days(ts) -> float:
    try:
        ts = int(ts or 0)
        if ts <= 0:
            return -1.0
        return (datetime.now(CN_TZ) - datetime.fromtimestamp(ts, CN_TZ)).total_seconds() / 86400.0
    except Exception:
        return -1.0
```

### `bili_search`：加 `within_days` 与 `up`

```python
async def bili_search(keyword: str, num: int = 10, order: str = "totalrank",
                      within_days: int = 0) -> str:
    ...
    videos, skipped_old = [], 0
    for item in result.get("result", []):
        if len(videos) >= num:
            break
        ts = item.get("pubdate", 0)
        if within_days and within_days > 0:
            age = _age_days(ts)
            if age < 0 or age > within_days:
                skipped_old += 1
                continue
        mid = item.get("mid")
        videos.append({
            # ...原有字段...
            "pubdate": ts,
            "published": _fmt_ts(ts),
            "age_days": round(_age_days(ts), 1),
            "up": {"name": item.get("author", ""), "mid": mid,
                   "homepage": ("https://space.bilibili.com/%s" % mid) if mid else None},
        })
    out = {"keyword": keyword, "count": len(videos), "videos": videos}
    if within_days:
        out["within_days"] = within_days
        out["skipped_older_than_limit"] = skipped_old
        if not videos and skipped_old:
            out["hint"] = "这一页全超期被清空，不等于没有新视频；换 order=pubdate 再搜。"
    return json.dumps(out, ensure_ascii=False)
```

> ⚠️ 坑：`within_days` 配 `order=click` / `dm` 会返回 0 条 ——
> 按热度排的头部视频本身就超期，全被筛掉了。**不是 bug**，但要提示调用方换排序。

### `bili_video_info`：加发布时间与 UP 主页

```python
    return json.dumps({
        # ...原有字段...
        "up": {
            "name": info.get("owner", {}).get("name"),
            "mid": info.get("owner", {}).get("mid"),
            "homepage": ("https://space.bilibili.com/%s" % info.get("owner", {}).get("mid"))
                        if info.get("owner", {}).get("mid") else None,
        },
        "pubdate": info.get("pubdate", 0),
        "published": _fmt_ts(info.get("pubdate", 0)),
        "age_days": round(_age_days(info.get("pubdate", 0)), 1),
    }, ensure_ascii=False)
```

---

## 验证

```bash
# 1. 工具补丁生效？返回里应出现 published / age_days / up.homepage
python src/afyg.py extract BV1DRJe6wEGc

# 2. 数据层能读？应输出记录条数与统计
python src/afyg.py stats

# 3. 接口活着？
curl -s http://127.0.0.1:<DSH端口>/api/bili-duty/v1 | jq .endpoints
```
