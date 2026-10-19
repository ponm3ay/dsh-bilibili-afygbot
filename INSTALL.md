# 安装（两种方式，按你的情况选）

> 本插件**不改动** `dsh-bili-scroll`。
> 已经装过原插件的人可以放心加装 —— 原插件照常从上游更新。

---

## 方式 A：已经从原插件装了 `dsh-bili-scroll`（推荐）

你只要加装本插件，它会：

| 做什么 | 不做什么 |
|---|---|
| ✅ 旁挂一份「凹分向章程」到自己的目录 | ❌ 不覆盖原插件的 `duty.md` |
| ✅ 另开一个数据接口 `/api/bili-afyg/v1` | ❌ 不改原插件的 `index.js` / `vendor` / `patch` |
| ✅ 检测到原插件时在日志和接口里标注 `mode: augment` | ❌ 不动原插件的 npm 依赖版本 |

**原插件保持 `^0.1.2` 这样的正常依赖**，所以 `dsh plugin --profile <name> update` 照样能把它升到新版。

### 装法

```bash
# 把仓库地址粘给 DSH，让它执行：
dsh plugin --profile desktop add link:<你的仓库路径>
# 或从 git 装：
dsh plugin --profile desktop add github:ponm3ay/dsh-bilibili-afygbot
```

装完**完全退出 DSH 再打开**。

---

## 方式 B：全新安装（还没装原插件）

本插件**不包含**刷视频的能力 —— 那是 `dsh-bili-scroll` 的活。所以：

```bash
# 先装原插件（作者的）
dsh plugin --profile desktop add dsh-bili-scroll
# 再加装本插件
dsh plugin --profile desktop add github:ponm3ay/dsh-bilibili-afygbot
```

然后重启 DSH，去设置里装依赖、扫码登录 —— 那些步骤跟原插件一样。

---

## 两种模式的区别

| | 独立运行 `standalone` | 增强模式 `augment` |
|---|---|---|
| 前提 | 只有本插件 | 已装 `dsh-bili-scroll` |
| 数据接口 | ✅ 有 | ✅ 有 |
| 凹分章程 | ✅ 有（自己的目录） | ✅ 有（旁挂，不动原件的） |
| 刷视频能力 | ❌ 无 | ✅ 用原插件的 |

启动日志里会写清楚当前是哪种模式。

---

## 验证装好了没

```bash
# 1. 插件在不在
curl -s http://127.0.0.1:<DSH端口>/api/bili-afyg/v1

# 应该看到：
# {
#   "schema": "dsh.wuwa/afyg-record@1",
#   "link": { "plugin": "dsh-bili-scroll", "version": "0.1.2", "mode": "augment" },
#   "endpoints": [...]
# }
```

`link.mode` 是 `augment` 就说明检测到原插件了；`standalone` 说明只有本插件。

---

## 想改凹分规则？

改这里（**别去改原插件的**）：

```
$DSH_HOME/bili-afyg/duty.afyg.md
```

第一次启动会自动生成。想恢复默认就删掉它，下次启动会重建。

---

## 卸载

```bash
dsh plugin --profile desktop remove dsh-bili-afyg
```

原插件完全不受影响。

---

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
