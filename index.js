/**
 * dsh-bili-afyg —— 鸣潮凹分（椰果）数据层插件
 * ============================================================================
 * 设计原则（很重要，别改）：
 *
 * 1. 不碰 dsh-bili-scroll。
 *    我们只做两件事：给它补一份「凹分向章程」，以及另开一个数据接口。
 *    原插件的代码、vendor、patch、配置，一个字都不改。
 *
 * 2. 保留上游更新能力。
 *    原插件在 profile 里是正常 npm 依赖（"dsh-bili-scroll": "^0.1.2"），
 *    我们不走 patch-package、不改它的 node_modules。
 *    所以 dsh plugin update 照样能把它升到新版本。
 *
 * 3. 章程增强是「旁挂」不是「覆盖」。
 *    发现原插件存在时，把凹分向章程写到我们自己的目录，
 *    原插件自己的 duty.md 不动 —— 它升级后我们不会把它打回旧版。
 * ============================================================================
 */
import z from '@deepseek-ai/schemastery'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { bindData } from './lib/data.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const PKG_NAME = 'dsh-bili-afyg'

export const name = PKG_NAME

export const Config = z.object({
  enabled: z.boolean().default(true),
  dataDir: z.string().default(''),
  augmentBiliScroll: z.boolean().default(true),
})

/* ── 找 dsh-bili-scroll（只读，绝不修改） ── */

function findBiliScroll(ctx) {
  const candidates = []
  try {
    const profileDir = ctx?.get?.("profileContext")?.dir
    if (profileDir) candidates.push(join(profileDir, 'node_modules', 'dsh-bili-scroll'))
  } catch { /* 拿不到就算了 */ }
  let cur = HERE
  for (let i = 0; i < 6; i++) {
    candidates.push(join(cur, 'node_modules', 'dsh-bili-scroll'))
    cur = dirname(cur)
  }
  for (const c of candidates) {
    try {
      const pj = join(c, 'package.json')
      if (existsSync(pj)) {
        const pkg = JSON.parse(readFileSync(pj, 'utf8'))
        return { dir: c, version: pkg.version || 'unknown', home: pickBiliScrollHome() }
      }
    } catch { /* 继续找 */ }
  }
  return null
}

function pickBiliScrollHome() {
  const home = process.env.DSH_HOME || ''
  if (!home) return null
  for (const n of ['bili-duty', 'bili-scroll']) {
    const p = join(home, n)
    if (existsSync(p)) return p
  }
  return join(home, 'bili-duty')
}

/* ── 章程增强（旁挂） ── */

const AUGMENT_FILE = 'duty.afyg.md'

function buildAugmentCharter() {
  return [
    '# 凹分向增强章程（dsh-bili-afyg 追加层）',
    '',
    '> ⚠️ 这不是替换 duty.md，而是**追加规则**。',
    '> 用的时候把这份和原章程一起读；冲突处以「更严格的」为准。',
    '',
    '## 只收椰果（鸣潮终焉矩阵凹分）',
    '',
    '### 三档判定',
    '',
    '| 档位 | 特征词 | 处置 |',
    '|---|---|---|',
    '| **轮椅轴** | 轮椅、萌新、手残、无脑、放空大脑、一键、挂机、保姆级、0合轴 | ❌ 一律跳过，**不管多少分** |',
    '| **进阶手法** | 进阶、高阶、多合轴、循环轴演示、逐帧教学、长记号串 | ✅ 收 |',
    '| **巅峰手法** | 巅峰、极限、顶分、国服前列、手搓、满合轴、4R26居 级密度 | ✅✅ 最优先 |',
    '',
    '### 术语（读不懂标题就判不准）',
    '',
    '- 配队缩写 = 三个字连写：绯洛穗 / 爱达千 / 清达莫 / 露丽莫 / 景月露 …',
    '- 手法记号：R 大招 · E 技能 · Z 重击 · 居 居合 · 处 处决 · 开 第几轮起手',
    '- 4R26居 = 一轮 4 次大招 + 26 次居合 —— **记号越密越硬**',
    '- w = 万分；dps/wdps = 每秒伤害；S2-3 = 第二赛季第 3 期',
    '',
    '## 时效：只收近 5 天',
    '',
    'bili_search 带 within_days=5。超过 5 天的最多写进报告，**不发评论**。',
    '',
    '## 评论：只夸 UP + @ 主人',
    '',
    '✅ 夸分数猛、夸操作快、喊主人来看',
    '❌ **不总结手法细节**（外行点评会翻车）、不点评指导、不自我表扬',
    '',
    '## 每条必记数据',
    '',
    '挑中的每条追加一行 JSON 到 data/records.jsonl：',
    '',
    '- score.value **只存数字**（58444），不换算',
    '- team.abbr **只写认得出的队名**，认不出留空',
    '- source.up.homepage **必填**（UP 主页）',
    '- rotation **随缘**：扒到文字轴就照抄原文，没有就不写这个字段',
    '',
  ].join('\n')
}

function ensureAugmentFile(dataDir) {
  const f = join(dataDir, AUGMENT_FILE)
  if (!existsSync(f)) {
    mkdirSync(dataDir, { recursive: true })
    writeFileSync(f, buildAugmentCharter(), 'utf8')
    return { file: f, created: true }
  }
  return { file: f, created: false }
}

/* ── 数据层 ── */

function loadData(dataDir) {
  return bindData(dataDir)
}

/* ── 应用 ── */

export function apply(ctx, cfg) {
  const log = (m) => { try { ctx?.logger?.info?.(`[${PKG_NAME}] ${m}`) } catch { console.log(`[${PKG_NAME}] ${m}`) } }

  if (!cfg.enabled) { log('已停用（enabled=false）'); return }

  const home = process.env.DSH_HOME || join(HERE, '.home')
  const dataDir = cfg.dataDir || join(home, 'bili-afyg')
  mkdirSync(dataDir, { recursive: true })

  const scroll = findBiliScroll(ctx)

  let aug = null
  if (cfg.augmentBiliScroll && scroll) {
    aug = ensureAugmentFile(dataDir)
    log(`检测到 dsh-bili-scroll v${scroll.version}（未改动它）→ 旁挂章程 ${aug.file}`)
  } else if (!scroll) {
    log('未检测到 dsh-bili-scroll —— 本插件独立运行，只提供数据层')
  }

  try {
    const data = loadData(dataDir)
    ctx.effect(() => ctx.webServer.register({
      kind: 'prefix',
      path: '/api/bili-afyg',
      handler: async (req, res) => {
        const send = (code, obj, ctype) => {
          const body = typeof obj === 'string' ? obj : JSON.stringify(obj)
          res.writeHead(code, {
            'content-type': ctype || 'application/json; charset=utf-8',
            'access-control-allow-origin': '*',
            'cache-control': 'no-store',
          })
          res.end(body)
        }
        try {
          const url = new URL(req.url, 'http://127.0.0.1')
          const sub = url.pathname.replace('/api/bili-afyg', '').replace(/^\/+/, '').replace(/\/+$/, '')
          if (sub === '' || sub === 'v1') return send(200, { ...data.OPENAPI,
            link: scroll ? { plugin: 'dsh-bili-scroll', version: scroll.version, mode: 'augment' } : { mode: 'standalone' } })
          if (sub === 'v1/health') return send(200, { ok: true, records: data.readAll().length })
          if (sub === 'v1/schema') return send(200, data.SCHEMA)
          if (sub === 'v1/stats') return send(200, data.stats())
          if (sub === 'v1/records') {
            const q = url.searchParams
            return send(200, data.query({
              kind: q.get('kind') || undefined, team: q.get('team') || undefined,
              tier: q.get('tier') || undefined, q: q.get('q') || undefined,
              sort: q.get('sort') || 'new',
              limit: q.get('limit') || 50, offset: q.get('offset') || 0,
            }))
          }
          if (sub === 'v1/export') {
            const fmt = url.searchParams.get('format') || 'jsonl'
            const rows = data.readAll()
            if (fmt === 'afyg') return send(200, { projects: rows.map(data.exportAfyg) })
            return send(200, rows.map((r) => JSON.stringify(r)).join('\n') + (rows.length ? '\n' : ''),
                        'application/x-ndjson; charset=utf-8')
          }
          return send(404, { error: 'unknown path', hint: 'GET /api/bili-afyg/v1' })
        } catch (e) {
          return send(500, { error: String(e?.message ?? e) })
        }
      },
    }), 'bili-afyg: /api/bili-afyg 路由')
    log(`数据接口已挂：/api/bili-afyg/v1  （数据目录 ${dataDir}）`)
  } catch (e) {
    log(`数据接口没挂上：${e?.message ?? e}`)
  }

  log(`就绪 · 模式=${scroll ? 'augment（增强 dsh-bili-scroll）' : 'standalone'}`)
}