# dsh-bilibili-afygbot

> 把 B站 上刷到的**鸣潮凹分（椰果）**视频，沉淀成**结构化、可联邦、可被别的 agent 调用**的数据。

[![powered by dsh](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![status](https://img.shields.io/badge/status-early%20preview-orange?style=flat-square)

---

> **本项目基于开源插件 [`dsh-bili-scroll`](https://github.com/lll-77777777/dsh-bili-scroll) 制作。**
>
> 插件作者：GitHub [**lll-77777777**](https://github.com/lll-77777777) · B站 [**@凌羽clover**](https://space.bilibili.com/354813103)
>
> 没有这个插件就没有本项目的一切 —— 先去给作者点个 star ⭐

---

## 这是什么

一套**数据层**，配合开源插件 [`dsh-bili-scroll`](https://github.com/lll-77777777/dsh-bili-scroll) 使用。

插件本来会每天刷 B站、挑视频、写日报 —— 但日报是给人看的，数据死在 markdown 里。
本项目把每一轮的结果**同时**落成结构化记录：

```
data/records.jsonl      # 一行一条，append-only
```

并对外提供只读 HTTP 接口，让别的工具、别的开发者、别的 agent 能直接消费。

**核心设计：记录 id 全局唯一**（`r_<BV号>_<kinds>`）。
所以每台装了插件的机器都是一份独立的数据源，**多份数据按 id 去重就能合并，不需要中心服务器**。

---

## 为什么做这个

刷凹分视频时，真正有价值的信息是**零散的** —— 配队、配置、出分、文字轴，
散在标题、简介、评论区里，看过就忘，攒不起来。

本项目补的就是这一头：**「从视频里扒出实际有人打出了什么」** —— 实战样本。

数据落在本地，接口开在本地，**你攒的样本是你自己的**。

---

## 安装

**两种模式，按你的情况选：**

| 你的情况 | 装法 |
|---|---|
| 已经装了 `dsh-bili-scroll` | 直接加装本插件 —— **不改动原插件，它照常从上游更新** |
| 还没装过 | 先装原插件，再加装本插件 |

```bash
# 加装（已装原插件的情况）
dsh plugin --profile desktop add github:ponm3ay/dsh-bilibili-afygbot

# 全新（先原插件，再本插件）
dsh plugin --profile desktop add dsh-bili-scroll
dsh plugin --profile desktop add github:ponm3ay/dsh-bilibili-afygbot
```

装完**完全退出 DSH 再打开**。

> **为什么加装不会影响原插件？**
> 本插件的 patch 用 `- insert:` 追加自己的 id（`bili-afyg`），不是替换任何现有条目；
> 它会检测原插件，但**只读不写** —— 章程是旁挂到自己目录的（`$DSH_HOME/bili-afyg/duty.afyg.md`）。
> 原插件在 profile 里仍是正常 npm 依赖（`^0.1.2`），所以 `dsh plugin update` 照样能升级它。

详细步骤见 [INSTALL.md](INSTALL.md)。

---
## 快速开始（不需要插件，只要数据层）

### 1. 只想要 HTTP 接口（不装插件）

```bash
git clone https://github.com/ponm3ay/dsh-bilibili-afygbot.git
cd dsh-bilibili-afygbot
python src/afyg.py serve --port 8787
```

然后：

```bash
curl -s http://127.0.0.1:8787/v1 | jq .            # 接口清单
curl -s http://127.0.0.1:8787/v1/stats | jq .      # 统计
```

（零第三方依赖，Python 3.9+ 即可。）

### 2. 从 B站 抓取（需要 MCP 工具箱）

抓取依赖 `dsh-bili-scroll` 自带的 `mcp_server.py`。准备方式见 [patches/README.md](patches/README.md)。

```bash
export AFYG_MCP=/path/to/mcp_server.py
export AFYG_PYTHON=/path/to/python            # 跑 MCP 的解释器（要装了 bilibili-api）
python src/afyg.py backfill BV1DRJe6wEGc BV19gJm6zEpP
python src/afyg.py list --tier peak
```

### 3. 接到插件里（推荐）

把 `src/data.mjs` 放进 `dsh-bili-scroll/lib/`，并在 `index.js` 里挂上路由 —— 代码见 [patches/README.md](patches/README.md)。
之后接口直接在 DSH 端口下：`/api/bili-duty/v1/*`。

---

## 数据模型

一条记录（完整 schema 见 [`schema/afyg-record.v1.json`](schema/afyg-record.v1.json)）：

```json
{
  "schema": "dsh.wuwa/afyg-record@1",
  "id": "r_BV1DRJe6wEGc_rotation-score",
  "kinds": ["rotation", "score"],
  "source": {
    "platform": "bilibili",
    "bvid": "BV1DRJe6wEGc",
    "url": "https://www.bilibili.com/video/BV1DRJe6wEGc",
    "title": "…绯洛穗4R17居58444无宝箱25buff…",
    "publishedAt": "2026-10-17 14:41",
    "ageDays": 1.5,
    "up": { "name": "…", "mid": 376166553,
            "homepage": "https://space.bilibili.com/376166553" }
  },
  "team": { "abbr": "绯洛穗" },
  "rotation": {
    "hasText": true,
    "text": "蚊子轴↓启动轴：月EQ闪 露RE 月跳闪E 露aaa …",
    "where": "comment",
    "evidenceUrl": "https://www.bilibili.com/video/BV1DRJe6wEGc"
  },
  "score": { "value": 58444, "unit": "score", "raw": "58444",
             "mode": "matrix", "season": "S2-3", "tier": "peak" },
  "capturedAt": "2026-10-19T02:15:09+08:00",
  "capturedBy": "dsh-bili-scroll/0.1.2"
}
```

### 三条记录规则

| 规则 | 说明 |
|---|---|
| **分数只存数字** | 标题写没写「分」字都算分。`raw` 保留原数字，不做 w→万 之类换算 |
| **配队只认词表** | 内置 30+ 常见队名，也可在 `data/teams.txt` 追加。**认不出就留空，不猜** |
| **文字轴随缘** | 认「文字轴 / 蚊子轴 / 蚊子粥」这类记谱；扒不到就不写这个字段 |

**UP 主页是硬要求** —— 每条记录都必须能回源核对。

### 档位

`wheelchair`（轮椅轴，有手就行）＜ `advanced`（进阶手法）＜ `peak`（巅峰手法）。

---

## HTTP API

只读、免鉴权、带 CORS。完整说明见 [`docs/api.md`](docs/api.md)。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/v1` | 接口清单（自描述，先看这个） |
| GET | `/v1/health` | 存活 + 记录数 |
| GET | `/v1/schema` | JSON Schema |
| GET | `/v1/stats` | 聚合统计 |
| GET | `/v1/records` | 列表，支持 `kind/team/tier/mode/season/q/since/limit/offset/sort` |
| GET | `/v1/records/{id}` | 单条 |
| GET | `/v1/teams` · `/v1/teams/{abbr}` | 按配队聚合 |
| GET | `/v1/ups` · `/v1/ups/{mid}` | 按 UP 聚合 |
| GET | `/v1/export?format=jsonl|afyg` | 整库导出 / 工程骨架 |
| POST | `/v1/records` | **预留**（501） |
| POST | `/v1/export/afyg` | **预留**（501） |

### 联邦聚合

没有中心服务器，靠 id 约定：

```python
import json, urllib.request

def pull(base):
    with urllib.request.urlopen(base + "/v1/records?limit=5000", timeout=20) as r:
        return json.loads(r.read().decode())["records"]

merged = {}
for base in ("http://127.0.0.1:8787", "http://其它实例:8787"):
    for rec in pull(base):
        old = merged.get(rec["id"])
        # 冲突以 capturedAt 较新的为准
        if not old or rec["capturedAt"] > old["capturedAt"]:
            merged[rec["id"]] = rec
```

---

## CLI 命令

```bash
python src/afyg.py extract  BV1xxx...     # 抓取并打印（不落盘）
python src/afyg.py backfill BV1xxx...     # 抓取并入库（自动去重）
python src/afyg.py ingest   file.json      # 外部 JSON 入库（会校验）
python src/afyg.py list     --kind score --tier peak
python src/afyg.py get      r_BV1xxx_score
python src/afyg.py stats
python src/afyg.py validate                # 全量校验（CI 友好，非 0 退出）
python src/afyg.py export   --format afyg  # 导出工程骨架（干跑）
python src/afyg.py serve    --port 8787
```

环境变量：

| 变量 | 作用 |
|---|---|
| `AFYG_DATA` | 数据目录（默认 `<repo>/data`） |
| `AFYG_MCP` | `mcp_server.py` 路径 |
| `AFYG_PYTHON` | 跑 MCP 的解释器 |
| `AFYG_SCHEMA` | schema 文件路径 |

---

## 目录结构

```
.
├── src/
│   ├── afyg.py            # 数据仓 CLI（零依赖）：抽取/校验/查询/API
│   └── data.mjs           # 插件侧数据层（node，零依赖）
├── schema/
│   └── afyg-record.v1.json
├── charter/
│   └── duty.zh-CN.md      # 定制章程示例（凹分向，含三档判定）
├── index.js               # 插件入口（apply / Config）
├── cordis.patch.yml       # 插件挂载声明（- insert: 追加，不替换）
├── lib/                   # 插件用的数据层
├── INSTALL.md             # 两种安装方式详解
├── patches/
│   └── README.md          # 怎么接进 dsh-bili-scroll（含 vendor 覆盖坑）
├── docs/
│   ├── api.md             # 接口详解
│   ├── blog.md            # 完整改造长文（2 万字）
│   └── onepager.png       # 一图流
├── examples/
│   └── records.sample.jsonl
└── scripts/
    └── render.cjs         # HTML → PDF / PNG（Playwright）
```

---

## 已知限制

> ⚠️ **early preview —— 数据接口尚未在运行中的插件里实测过。**
> 数据格式、抽取管线、离线校验都已跑通（见 `validate` 与真实 HTTP 请求）；
> 但插件的 HTTP 路由要**重启 DSH 才会加载**，字段命名与边界行为仍可能调整。**别当稳定 API 用。**

其他限制，如实列：

- **不做自动登分 / 自动传轴**。`POST` 接口是预留位，返回 501。真正的上传需要工坊授权与审核。
- **精度差一档**：工坊的工程是「算出来的」，这里的记录是「从视频里扒的」。宁可 `confidence` 低，也不把估算写成实测。
- **配队识别靠词表**，冷门队名认不出会留空。
- **文字轴覆盖率低** —— 大多数视频根本不贴轴，这是常态，不是 bug。
- **B站 接口无官方机器人 API**，抓取走的是 web 端点，可能因风控失效。

---

## 风险提示

- 本项目产生的数据来自公开视频；**评论 / @ 功能请自行评估账号风险**，建议先只写数据不发评论。
- 请遵守 B站 用户协议与 robots 约定，控制请求频率。
- 引用他人视频内容时**保留出处**（本 schema 强制带 `source.url` 与 `up.homepage`）。

---

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。欢迎补充队名词表、修抽取规则、对接更多数据源。

## 许可

[MIT](LICENSE) · 基于 [`dsh-bili-scroll`](https://github.com/lll-77777777/dsh-bili-scroll)（MIT）

---

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)