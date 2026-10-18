# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-10-19

首个公开版本（early preview）。

### Added

- **数据模型** `dsh.wuwa/afyg-record@1` + JSON Schema
  - 记分：配队 / 配置 / 分数 / 赛季 / 档位
  - 文字轴：原文 + 出处 + 记号（tokens）
  - 必带 UP 主页，保证可回源核对
- **`src/afyg.py`** —— 零依赖 CLI
  - `extract` / `backfill`：从 B站 视频抓取并结构化
  - `ingest` / `list` / `get` / `stats` / `validate` / `export`
  - `serve`：只读 HTTP API
- **`src/data.mjs`** —— 插件侧数据层（node，零依赖）
  - 归一化 / 校验 / 查询 / 统计 / 工程骨架导出
  - `OPENAPI` 自描述清单
- **HTTP API**（`/v1/*`）
  - `health` / `schema` / `stats` / `records` / `records/{id}`
  - `teams` / `ups` 聚合
  - `export?format=jsonl|afyg`
  - `POST` 写接口预留（501）
- **`charter/duty.zh-CN.md`** —— 凹分向定制章程示例
  - 三档判定：轮椅轴跳过 / 进阶收 / 巅峰优先
  - 时效硬条件：只收近 5 天，超期不发评论
  - 评论规范：报喜 + 夸 UP + @ 主人，禁自我表扬
- **文档**
  - `README.md`、`docs/api.md`、`docs/blog.md`（2 万字改造长文）、`docs/onepager.png`

### Known issues

- HTTP 路由**未在运行中的插件里实测**（需重启 DSH 加载），字段可能调整。
- 自动登分 / 上传轴**未实现**，仅预留接口。
- 配队识别依赖词表，冷门队名会留空。
- 文字轴覆盖率天然偏低（多数视频不贴轴）。
