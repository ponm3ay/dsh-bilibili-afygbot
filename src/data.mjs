/**
 * 椰果数据层 —— 把每轮刷出来的「凹分轴 / 出分」沉淀成可被别的工具消费的数据。
 *
 * 设计要点（2026-10-19 主人定方向）：
 *   · 不是「某台机器的本地脚本」，而是**插件自带的数据源**：谁装了 dsh-bili-scroll，
 *     谁的每一轮产出就是一份可对接的库，通过本插件的 HTTP 端口对外提供。
 *   · 记录 ID 全局唯一（BV 号 + 类型），所以多实例天然可合并 —— 联邦聚合不需要
 *     中心服务器，按 id 去重即可。
 *   · schema 自我描述（GET /v1/schema），版本号写进每条记录，别的 agent 不必猜。
 *   · 本模块零依赖（只用 node 内置）。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync, appendFileSync } from 'node:fs'
import { join } from 'node:path'
import { randomBytes } from 'node:crypto'

export const SCHEMA_ID = 'dsh.wuwa/afyg-record@1'
export const KINDS = ['rotation', 'score']
export const TIERS = ['wheelchair', 'advanced', 'peak']
export const UNITS = ['score', 'dps', 'seconds']
export const MODES = ['matrix', 'toa', 'other']
export const WHERE = ['comment', 'description', 'subtitle', 'onscreen', 'pinned', 'video']

const CN_OFFSET_MS = 8 * 3600 * 1000
export const nowIso = () => new Date(Date.now() + CN_OFFSET_MS).toISOString().replace('Z', '+08:00').slice(0, 19) + '+08:00'

/* ─────────────────── 实例标识（联邦聚合用） ─────────────────── */

export function instanceId(stateDir) {
  const f = join(stateDir, 'data', '.instance')
  try {
    if (existsSync(f)) return readFileSync(f, 'utf8').trim()
    mkdirSync(join(stateDir, 'data'), { recursive: true })
    const id = 'inst_' + randomBytes(9).toString('hex')
    writeFileSync(f, id, 'utf8')
    return id
  } catch { return 'inst_unknown' }
}

/* ─────────────────── Schema ─────────────────── */

export const SCHEMA = {
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  $id: SCHEMA_ID,
  title: '鸣潮凹分记录',
  description: '由 dsh-bili-scroll 每轮刷视频产出的一条结构化记录。只读消费；写入走插件内部。',
  type: 'object',
  required: ['schema', 'id', 'kinds', 'source', 'capturedAt', 'capturedBy'],
  properties: {
    schema: { const: SCHEMA_ID },
    id: { type: 'string', description: '全局唯一：r_<BV号>_<kind 组合>' },
    kinds: { type: 'array', items: { enum: KINDS }, description: '同一视频可同时是 rotation 和 score' },
    source: {
      type: 'object',
      required: ['platform', 'bvid', 'url', 'up'],
      properties: {
        platform: { const: 'bilibili' },
        bvid: { type: 'string' },
        url: { type: 'string' },
        title: { type: 'string' },
        publishedAt: { type: 'string', description: '北京时间 YYYY-MM-DD HH:MM' },
        ageDays: { type: 'number' },
        up: {
          type: 'object',
          required: ['homepage'],
          properties: {
            name: { type: ['string', 'null'] },
            mid: { type: ['integer', 'null'] },
            homepage: { type: 'string', description: '硬要求：UP 主页链接' },
          },
        },
        stats: { type: 'object' },
      },
    },
    team: {
      type: 'object',
      properties: {
        abbr: { type: 'string', description: '配队缩写，如 绯洛穗' },
        members: { type: 'array', items: { type: 'string' } },
        chain: { type: 'string', description: '共鸣链串，如 0161' },
        refinement: { type: 'string' },
        slots: { type: 'array', items: { type: 'object' } },
      },
    },
    rotation: {
      type: 'object',
      description: '文字轴（手法记谱）—— 本数据最值钱的部分',
      properties: {
        hasText: { type: 'boolean' },
        text: { type: ['string', 'null'], description: '原文，不做改写' },
        format: { enum: ['notation', 'freeform'] },
        where: { enum: WHERE },
        evidenceUrl: { type: 'string' },
        tokens: { type: 'array', items: { type: 'string' } },
      },
    },
    score: {
      type: 'object',
      properties: {
        value: { type: ['integer', 'null'] },
        unit: { enum: UNITS },
        raw: { type: 'string', description: '标题原文，不换算' },
        mode: { enum: MODES },
        season: { type: 'string' },
        tier: { enum: TIERS },
      },
    },
    tags: { type: 'array', items: { type: 'string' } },
    capturedAt: { type: 'string' },
    capturedBy: { type: 'string' },
    confidence: { type: 'number', minimum: 0, maximum: 1 },
    origin: { type: 'object', description: '联邦聚合用：哪个实例产出的' },
    notes: { type: 'string' },
  },
}

/* ─────────────────── 归一化 / 校验 ─────────────────── */

export const recordId = (r) => {
  const bv = String(r?.source?.bvid || '').trim()
  const k = (r?.kinds || []).slice().sort().join('-') || 'x'
  return 'r_' + bv + '_' + k
}

export function normalize(r, stateDir) {
  const o = { ...r }
  o.schema = o.schema || SCHEMA_ID
  o.kinds = Array.isArray(o.kinds) ? o.kinds : []
  o.tags = Array.isArray(o.tags) ? o.tags : []
  o.capturedAt = o.capturedAt || nowIso()
  o.capturedBy = o.capturedBy || 'dsh-bili-scroll/0.1.2'
  o.source = { ...(o.source || {}) }
  const up = { ...(o.source.up || {}) }
  if (up.mid && !up.homepage) up.homepage = 'https://space.bilibili.com/' + up.mid
  o.source.up = up
  o.id = o.id || recordId(o)
  if (stateDir && !o.origin) o.origin = { instanceId: instanceId(stateDir) }
  return o
}

export function validate(r) {
  const e = []
  if (!r || typeof r !== 'object') return ['record must be an object']
  if (r.schema !== SCHEMA_ID) e.push('schema must be ' + SCHEMA_ID)
  for (const k of ['kinds', 'source', 'capturedAt', 'capturedBy']) if (!r[k]) e.push('missing ' + k)
  const s = r.source || {}
  if (!s.bvid) e.push('missing source.bvid')
  if (!s.url) e.push('missing source.url')
  if (!(s.up || {}).homepage) e.push('missing source.up.homepage (硬要求：UP 主页链接)')
  for (const k of r.kinds || []) if (!KINDS.includes(k)) e.push('unknown kind ' + k)
  const sc = r.score || {}
  if (sc.tier && !TIERS.includes(sc.tier)) e.push('unknown tier ' + sc.tier)
  if (sc.unit && !UNITS.includes(sc.unit)) e.push('unknown unit ' + sc.unit)
  if (sc.mode && !MODES.includes(sc.mode)) e.push('unknown mode ' + sc.mode)
  const ro = r.rotation || {}
  if (ro.where && !WHERE.includes(ro.where)) e.push('unknown rotation.where ' + ro.where)
  if (ro.hasText && !ro.text) e.push('rotation.hasText=true 但 text 为空')
  return e
}

/* ─────────────────── 存储 ─────────────────── */

const recFile = (stateDir) => join(stateDir, 'data', 'records.jsonl')

export function readAll(stateDir) {
  const f = recFile(stateDir)
  if (!existsSync(f)) return []
  const out = []
  for (const line of readFileSync(f, 'utf8').split('\n')) {
    const t = line.trim()
    if (!t) continue
    try { out.push(JSON.parse(t)) } catch { /* 坏行跳过，不让一条脏数据毁掉整库 */ }
  }
  return out
}

export function append(stateDir, recs) {
  const list = Array.isArray(recs) ? recs : [recs]
  const seen = new Set(readAll(stateDir).map((r) => r.id))
  const added = [], skipped = []
  const buf = []
  for (const raw of list) {
    const r = normalize(raw, stateDir)
    const errs = validate(r)
    if (errs.length) { skipped.push({ id: r.id, reason: errs }); continue }
    if (seen.has(r.id)) { skipped.push({ id: r.id, reason: ['duplicate'] }); continue }
    seen.add(r.id)
    buf.push(JSON.stringify(r))
    added.push(r.id)
  }
  if (buf.length) {
    try {
      mkdirSync(join(stateDir, 'data'), { recursive: true })
      appendFileSync(recFile(stateDir), buf.join('\n') + '\n', 'utf8')
    } catch (e) { return { added: [], skipped: [...skipped, { id: '-', reason: ['write failed: ' + e.message] }] } }
  }
  return { added, skipped }
}

/* ─────────────────── 查询 / 统计 ─────────────────── */

export function query(stateDir, p = {}) {
  let rows = readAll(stateDir)
  const kind = p.kind, team = p.team, tier = p.tier, mode = p.mode, season = p.season
  const q = (p.q || '').toLowerCase(), since = p.since
  rows = rows.filter((r) => {
    if (kind && !(r.kinds || []).includes(kind)) return false
    if (team && !String((r.team || {}).abbr || '').toLowerCase().includes(team.toLowerCase())) return false
    const sc = r.score || {}
    if (tier && sc.tier !== tier) return false
    if (mode && sc.mode !== mode) return false
    if (season && sc.season !== season) return false
    if (since && String((r.source || {}).publishedAt || '') < since) return false
    if (q && !JSON.stringify(r).toLowerCase().includes(q)) return false
    return true
  })
  const total = rows.length
  if (p.sort === 'score') rows.sort((a, b) => ((b.score || {}).value || 0) - ((a.score || {}).value || 0))
  else rows.sort((a, b) => String((b.source || {}).publishedAt || '').localeCompare(String((a.source || {}).publishedAt || '')))
  const limit = Math.min(Number(p.limit) || 50, 500)
  const offset = Number(p.offset) || 0
  return { total, count: rows.slice(offset, offset + limit).length, records: rows.slice(offset, offset + limit) }
}

const countBy = (rows, f) => {
  const d = {}
  for (const r of rows) { const k = f(r); if (k == null) continue; d[k] = (d[k] || 0) + 1 }
  return Object.fromEntries(Object.entries(d).sort((a, b) => b[1] - a[1]))
}

export function stats(stateDir) {
  const rows = readAll(stateDir)
  return {
    total: rows.length,
    kinds: countBy(rows, (r) => (r.kinds || []).length ? r.kinds.slice().sort().join('+') : null),
    tiers: countBy(rows, (r) => (r.score || {}).tier),
    modes: countBy(rows, (r) => (r.score || {}).mode),
    withRotationText: rows.filter((r) => (r.rotation || {}).hasText).length,
    withUpHomepage: rows.filter((r) => ((r.source || {}).up || {}).homepage).length,
    teams: countBy(rows, (r) => (r.team || {}).abbr),
    instance: instanceId(stateDir),
    generatedAt: nowIso(),
  }
}

/** 给「椰果工坊」工程格式的干跑映射（预留位，不发布） */
export function exportAfyg(r) {
  const src = r.source || {}, team = r.team || {}
  return {
    schema: 'dsh.wuwa/afyg-project-draft@1',
    note: '干跑：字段缺失处为 null，未调用工坊写接口。',
    title: (team.abbr || '') + ' · ' + ((r.score || {}).raw || src.title || ''),
    authorName: null,
    tags: r.tags || [],
    teamPreview: { names: team.members || [], slots: team.slots || [] },
    rotationText: (r.rotation || {}).text || null,
    score: r.score || null,
    provenance: { platform: 'bilibili', bvid: src.bvid, url: src.url, up: (src.up || {}).homepage },
    publish: null,
  }
}

/* ─────────────────── OpenAPI 风格的接口清单 ─────────────────── */

export const OPENAPI = {
  schema: SCHEMA_ID,
  base: '/api/bili-duty/v1',
  auth: '只读接口无需鉴权（本机回环）；写接口为预留位，当前 501。',
  federation: '记录 id 全局唯一（r_<BV>_<kinds>），多实例合并只需按 id 去重，无需中心服务器。',
  endpoints: [
    { method: 'GET', path: '/api/bili-duty/v1', desc: '接口清单（本对象）' },
    { method: 'GET', path: '/api/bili-duty/v1/health', desc: '存活 + 记录数' },
    { method: 'GET', path: '/api/bili-duty/v1/schema', desc: 'JSON Schema（自描述）' },
    { method: 'GET', path: '/api/bili-duty/v1/stats', desc: '聚合统计' },
    { method: 'GET', path: '/api/bili-duty/v1/records', query: 'kind,team,tier,mode,season,q,since,limit,offset,sort(new|score)', desc: '记录列表' },
    { method: 'GET', path: '/api/bili-duty/v1/records/{id}', desc: '单条记录' },
    { method: 'GET', path: '/api/bili-duty/v1/teams', desc: '按配队聚合' },
    { method: 'GET', path: '/api/bili-duty/v1/teams/{abbr}', desc: '某配队全部记录' },
    { method: 'GET', path: '/api/bili-duty/v1/ups', desc: '按 UP 聚合' },
    { method: 'GET', path: '/api/bili-duty/v1/ups/{mid}', desc: '某 UP 全部记录' },
    { method: 'GET', path: '/api/bili-duty/v1/export', query: 'format=jsonl|afyg', desc: '整库导出' },
    { method: 'POST', path: '/api/bili-duty/v1/records', reserved: true, desc: '外部写入（预留）' },
    { method: 'POST', path: '/api/bili-duty/v1/export/afyg', reserved: true, desc: '一键登分/上传轴（预留）' },
  ],
}
