/* Unit tests for thinks.ts (B3 — thinking-marker bug from the public review).
   Two cases fail against the pre-fix code:
   - mid-sentence " thinking" in prose is swallowed into a thinking block
   - a literal "<think>" inside prose is over-normalized into a marker
   Markers use the REAL emitted format: ` thinking` / ` response` each on
   their own line (line-boundary only).
   Run:  cd frontend && npx vitest run src/pages/chat/thinks.test.ts
*/
import { describe, expect, it } from 'vitest'

import { parseThinks } from './thinks'

describe('parseThinks', () => {
  it('splits a tagged thinking block from the answer', () => {
    const r = parseThinks(' thinking\nLet me think carefully.\n response\nThe answer is 42.', false)
    expect(r.thinks).toEqual(['Let me think carefully.'])
    expect(r.main).toBe('The answer is 42.')
  })

  it('does NOT treat mid-sentence "thinking" in prose as a marker', () => {
    const src = 'I was thinking about this problem for a while, and the answer is 42.'
    const r = parseThinks(src, false)
    expect(r.thinks).toEqual([])
    expect(r.partial).toBeNull()
    expect(r.main).toBe(src)
  })

  it('does NOT treat "response" in prose as a close marker', () => {
    const src = 'The quick response came back: "ok".'
    const r = parseThinks(src, false)
    expect(r.thinks).toEqual([])
    expect(r.main).toBe(src)
  })

  it('normalizes XML think tags at line boundaries', () => {
    const r = parseThinks('\n<think>\nLet me check\n</think>\nThe answer is 42.', false)
    expect(r.thinks).toEqual(['Let me check'])
    expect(r.main).toBe('The answer is 42.')
  })

  it('keeps a literal "<think>" inside prose as text', () => {
    const src = 'The model emitted <think> as a literal tag example.'
    const r = parseThinks(src, false)
    expect(r.thinks).toEqual([])
    expect(r.partial).toBeNull()
    expect(r.main).toBe(src)
  })

  it('exposes an open block as partial while streaming', () => {
    const r = parseThinks(' thinking\nStill reasoning...', true)
    expect(r.partial).toBe('Still reasoning...')
    expect(r.main).toBe('')
  })

  it('holds back a partial trailing marker fragment while streaming', () => {
    const r = parseThinks('The answer is coming. thinki', true)
    // ' thinki' (with its separator space) is held back until the marker
    // completes; a live empty block opens in the meantime.
    expect(r.main).toBe('The answer is coming.')
    expect(r.partial).toBe('')
  })
})
