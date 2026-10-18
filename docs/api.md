# API 参考

> Schema: `dsh.wuwa/afyg-record@1`
> 状态：**early preview** —— 未在运行中的插件里实测，字段可能调整。

## 约定

- 所有接口位于 `<base>/v1`，`base` 依部署方式不同：
  - 独立运行：`http://127.0.0.1:8787`
  - 接进插件：`http://127.0.0.1:<DSH端口>/api/bili-duty`
- **只读**接口免鉴权，带 CORS（`access-control-allow-origin: *`）。
- 响应 `application/json; charset=utf-8`；`export?format=jsonl` 是 `application/x-ndjson`。
- 时间统一北京时间，格式 `YYYY-MM-DD HH:MM`。

---

## GET /v1

接口清单（自描述）。**先调这个**，不用猜字段。

```json
{
  "schema": "dsh.wuwa/afyg-record@1",
  "base": "/v1",
  "auth": "只读接口无需鉴权；写接口为预留位，当前 501。",
  "federation": "记录 id 全局唯一（r_<BV>_<kinds>），多实例合并只需按 id 去重，无需中心服务器。",
  "endpoints": [ { "method": "GET", "path": "/v1/health", "desc": "存活 + 记录数" }, ... ],
  "instance": "inst_xxxxxxxxxx"
}
```

## GET /v1/health

```json
{ "ok": true, "records": 42, "instance": "inst_xxx", "schema": "dsh.wuwa/afyg-record@1", "time": 1792293000000 }
```

## GET /v1/schema

返回 JSON Schema（见 [`schema/afyg-record.v1.json`](../schema/afyg-record.v1.json)）。

## GET /v1/stats

```json
{
  "total": 42,
  "kinds": { "score": 20, "rotation": 12, "rotation+score": 10 },
  "tiers": { "peak": 18, "advanced": 22, "wheelchair": 2 },
  "modes": { "matrix": 40, "toa": 2 },
  "withRotationText": 11,
  "withUpHomepage": 42,
  "teams": { "绯洛穗": 6, "露丽莫": 5 },
  "instance": "inst_xxx",
  "generatedAt": "2026-10-19T02:15:09+08:00"
}
```

## GET /v1/records

查询参数（全部可选）：

| 参数 | 说明 | 示例 |
|---|---|---|
| `kind` | `score` / `rotation` | `?kind=score` |
| `team` | 配队缩写，模糊匹配 | `?team=绯洛穗` |
| `tier` | `wheelchair` / `advanced` / `peak` | `?tier=peak` |
| `mode` | `matrix` / `toa` / `other` | `?mode=matrix` |
| `season` | 赛季，精确匹配 | `?season=S2-3` |
| `q` | 全文关键词（含标题、轴正文） | `?q=满延` |
| `since` | 发布时间下界 | `?since=2026-10-14` |
| `sort` | `new`（默认）/ `score` | `?sort=score` |
| `limit` | 每页条数，默认 50，上限 500 | `?limit=20` |
| `offset` | 偏移 | `?offset=40` |

```json
{ "total": 12, "count": 12, "records": [ { "...": "..." } ] }
```

## GET /v1/records/{id}

单条。没找到返回 `404 { "error": "not found", "id": "..." }`。

id 形如 `r_BV1DRJe6wEGc_rotation-score`。

## GET /v1/teams · /v1/teams/{abbr}

```json
// /v1/teams
{ "total": 8, "teams": [ { "abbr": "绯洛穗", "count": 6, "members": [] } ] }

// /v1/teams/绯洛穗
{ "team": "绯洛穗", "count": 6, "records": [ ... ] }
```

## GET /v1/ups · /v1/ups/{mid}

```json
// /v1/ups
{ "total": 5, "ups": [ { "mid": 376166553, "name": "…", "homepage": "https://space.bilibili.com/376166553", "count": 3 } ] }

// /v1/ups/376166553
{ "mid": 376166553, "count": 3, "records": [ ... ] }
```

## GET /v1/export

| format | 返回 |
|---|---|
| `jsonl`（默认） | 整库 NDJSON，一行一条 |
| `afyg` | 工程骨架数组（`dsh.wuwa/afyg-project-draft@1`），干跑不发布 |

`afyg` 格式与 [椰果工坊](https://github.com/d4rkOfficial/wuwa-afyg-share/blob/master/docs/api.md) 的
`teamPreview` 对齐（角色 / 共鸣链 / 武器 / 谐振），便于将来导入工具箱。

## POST /v1/records · /v1/export/afyg

**预留位，当前返回 501。**

```json
{ "error": "reserved", "message": "写接口是预留位：设计已定、尚未启用。" }
```

设计意图：

- `POST /v1/records` —— 外部写入。别的工具抓到的分也能灌进同一个库（需鉴权 + 去重）。
- `POST /v1/export/afyg` —— 转成工程并上传到椰果工坊，实现「自动登分 + 自动传轴」。
  需要工坊的 `POST /api/public/projects` 与作者授权，涉及审核，故未实现。

---

## 联邦聚合

没有中心服务器。id 全局唯一，按 id 合并即可：

```python
import json, urllib.request

def pull(base):
    with urllib.request.urlopen(base + "/v1/records?limit=5000", timeout=20) as r:
        return json.loads(r.read().decode())["records"]

merged = {}
for base in ("http://127.0.0.1:8787", "http://another-host:8787"):
    for rec in pull(base):
        cur = merged.get(rec["id"])
        if not cur or rec["capturedAt"] > cur["capturedAt"]:   # 冲突以较新的为准
            merged[rec["id"]] = rec
print(len(merged))
```

## 错误码

| 状态码 | 含义 |
|---|---|
| 200 | 正常 |
| 404 | 路径或 id 不存在 |
| 405 | 方法不允许 |
| 501 | 预留接口，尚未启用 |
| 500 | 服务端异常（带 `error` 字段） |

---

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
