/* Translation verifier (spec §6.2 step 3)
   Checks each non-English locale against EN:
     - key-set parity (no missing / no extra keys)
     - {{placeholder}} integrity (same vars, same count per key)
     - valid JSON
     - length: TH > EN*1.45 → WARN (not a hard fail; Thai runs long)
   Exit 0 = pass, exit 1 = hard fail (missing/extra/placeholder/JSON). */
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const localesDir = join(root, 'locales')
const LEN_RATIO = 1.45

const enDir = join(localesDir, 'en')
if (!existsSync(enDir)) {
  console.error('No en/ locale found')
  process.exit(1)
}

function loadLang(dir) {
  const out = {}
  for (const f of readdirSync(dir).filter((f) => f.endsWith('.json'))) {
    const ns = f.replace(/\.json$/, '')
    out[ns] = JSON.parse(readFileSync(join(dir, f), 'utf8'))
  }
  return out
}

function flatten(obj, prefix = '', acc = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object') flatten(v, key, acc)
    else acc[key] = v
  }
  return acc
}

function placeholders(str) {
  return [...String(str).matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort().join(',')
}

const en = loadLang(enDir)
const enFlat = {}
for (const ns of Object.keys(en)) for (const [k, v] of Object.entries(flatten(en[ns]))) enFlat[`${ns}:${k}`] = v

const langs = readdirSync(localesDir).filter((d) => d !== 'en' && existsSync(join(localesDir, d, )))
let hardFail = 0
let warns = 0

for (const lang of langs) {
  console.log(`\n== ${lang} ==`)
  let langFlat
  try {
    langFlat = {}
    const loaded = loadLang(join(localesDir, lang))
    for (const ns of Object.keys(loaded)) for (const [k, v] of Object.entries(flatten(loaded[ns]))) langFlat[`${ns}:${k}`] = v
  } catch (e) {
    console.error(`  ✗ JSON parse error: ${e.message}`)
    hardFail++
    continue
  }
  const enKeys = new Set(Object.keys(enFlat))
  const langKeys = new Set(Object.keys(langFlat))
  const missing = [...enKeys].filter((k) => !langKeys.has(k))
  const extra = [...langKeys].filter((k) => !enKeys.has(k))
  if (missing.length) { console.error(`  ✗ missing keys (${missing.length}): ${missing.slice(0, 8).join(', ')}${missing.length > 8 ? '…' : ''}`); hardFail++ }
  if (extra.length) { console.error(`  ✗ extra keys (${extra.length}): ${extra.slice(0, 8).join(', ')}${extra.length > 8 ? '…' : ''}`); hardFail++ }

  let phMismatch = 0
  let longCount = 0
  for (const k of enKeys) {
    if (!langKeys.has(k)) continue
    const eph = placeholders(enFlat[k])
    const lph = placeholders(langFlat[k])
    if (eph !== lph) {
      if (phMismatch < 6) console.error(`  ✗ placeholder mismatch [${k}] en={${eph}} ${lang}={${lph}}`)
      phMismatch++
    }
    const enLen = String(enFlat[k]).length
    const langLen = String(langFlat[k]).length
    if (enLen >= 8 && langLen > enLen * LEN_RATIO) longCount++
  }
  if (phMismatch) { hardFail++; console.error(`  ✗ ${phMismatch} placeholder mismatches total`) }
  if (longCount) { warns++; console.warn(`  ⚠ ${longCount} strings > ${Math.round((LEN_RATIO - 1) * 100)}% longer than EN (review UI fit)`) }
  if (!missing.length && !extra.length && !phMismatch) {
    console.log(`  ✓ key parity + placeholders OK (${enKeys.size} keys)${longCount ? ` · ${longCount} long` : ''}`)
  }
}

console.log(`\n${hardFail ? '✗ FAIL' : '✓ PASS'}${warns ? ` (${warns} warnings)` : ''}`)
process.exit(hardFail ? 1 : 0)
