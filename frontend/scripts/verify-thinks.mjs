/* Verification for parseThinks — imports the REAL module from
   src/pages/chat/thinks.ts (no inline copy, so this test can never
   diverge from the source again). The previous inline copy kept the old
   `indexOf(TAG_OPEN, i)` logic and masked the .search() infinite-loop
   regression that froze the chat page on any completed thinking block.

   Requires Node with type stripping (>= 22.6 with --experimental-strip-types,
   or >= 23.6 by default).
   Run: node scripts/verify-thinks.mjs */
import { parseThinks } from '../src/pages/chat/thinks.ts'

// ' thinking' / ' response' — the exact markers the server emits.
const TAG_OPEN = ' thinking'
const TAG_CLOSE = ' response'

let pass = 0, fail = 0
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (ok) { pass++; console.log('  OK ' + name) }
  else { fail++; console.log('  FAIL ' + name + '\n    got: ' + JSON.stringify(actual) + '\n    exp: ' + JSON.stringify(expected)) }
}

console.log('=== tag-based blocks (regression) ===')
check('completed block', parseThinks('Hello ' + TAG_OPEN + ' secret ' + TAG_CLOSE + ' world', false), { main: 'Hello  world', thinks: [' secret '], partial: null })
check('open block streaming', parseThinks('Hello ' + TAG_OPEN + ' secret', true), { main: 'Hello ', thinks: [], partial: ' secret' })
check('no tags passthrough', parseThinks('plain text', false), { main: 'plain text', thinks: [], partial: null })
check('leading tag (no space before)', parseThinks(TAG_OPEN + '\nreason here\n' + TAG_CLOSE + '\nAnswer: 42', false), { main: '\nAnswer: 42', thinks: ['\nreason here\n'], partial: null })
check('leading tag streaming', parseThinks(TAG_OPEN + '\nstill thinking', true), { main: '', thinks: [], partial: '\nstill thinking' })
// Infinite-loop regression: two completed blocks in ONE message. The old
// .search() variant re-found block 1 forever and hung the main thread.
check('two completed blocks', parseThinks('A' + TAG_OPEN + ' one ' + TAG_CLOSE + 'X' + TAG_OPEN + ' two ' + TAG_CLOSE + 'Y', false), { main: 'AXY', thinks: [' one ', ' two '], partial: null })
// A block after a leading block must also be found (indexOf advances past 0).
check('leading block + second block', parseThinks(TAG_OPEN + 'A' + TAG_CLOSE + ' tail ' + TAG_OPEN + 'B' + TAG_CLOSE, false), { main: ' tail ', thinks: ['A', 'B'], partial: null })
check('leading open + close during streaming', parseThinks(TAG_OPEN + ' still going ' + TAG_CLOSE, true), { main: '', thinks: [' still going '], partial: null })

console.log('=== XML <think> tags (Qwen3/DeepSeek/R1 chat templates) ===')
// The backend streams raw model output; Qwen3/DeepSeek family models emit
// \n<think>…</think>\n blocks that must render as accordions like the
// internal markers. Normalisation happens inside parseThinks.
const X_OPEN = '<think>'
const X_CLOSE = '</think>'
check('xml completed block', parseThinks('Hello ' + X_OPEN + ' secret ' + X_CLOSE + ' world', false), { main: 'Hello  world', thinks: [' secret '], partial: null })
check('xml leading (no space) completed', parseThinks(X_OPEN + '\nreason here\n' + X_CLOSE + '\nAnswer: 42', false), { main: '\nAnswer: 42', thinks: ['\nreason here\n'], partial: null })
check('xml open block streaming', parseThinks(X_OPEN + '\nstill thinking', true), { main: '', thinks: [], partial: '\nstill thinking' })
check('xml two blocks', parseThinks('A ' + X_OPEN + ' one ' + X_CLOSE + ' X ' + X_OPEN + ' two ' + X_CLOSE + ' Y', false), { main: 'A  X  Y', thinks: [' one ', ' two '], partial: null })
check('xml partial open tail held back', parseThinks('pre <thi', true), { main: 'pre ', thinks: [], partial: '' })
check('xml partial close tail held back', parseThinks(X_OPEN + ' done </th', true), { main: '', thinks: [], partial: ' done ' })
check('xml full close during streaming', parseThinks(X_OPEN + ' done ' + X_CLOSE, true), { main: '', thinks: [' done '], partial: null })
check('xml closed then answer streaming', parseThinks(X_OPEN + ' secret ' + X_CLOSE + ' answer', true), { main: ' answer', thinks: [' secret '], partial: null })
// Regression: the internal markers still work after normalisation runs.
check('internal marker still works after xml code path', parseThinks('pre ' + TAG_OPEN + ' x ' + TAG_CLOSE + ' post', false), { main: 'pre  post', thinks: [' x '], partial: null })

console.log('=== verbal "Thinking Process:" fallback ===')
check('verbal completed with answer', parseThinks('Thinking Process: let me reason\nFinal answer: 42', false), { main: '\nFinal answer: 42', thinks: ['Thinking Process: let me reason'], partial: null })
check('verbal streaming (no separator yet)', parseThinks('Thinking Process: still thinking...', true), { main: '', thinks: [], partial: 'Thinking Process: still thinking...' })
check('verbal completed no separator', parseThinks('Thinking Process: all thinking', false), { main: '', thinks: ['Thinking Process: all thinking'], partial: null })
check('verbal Thai separator', parseThinks('Thinking Process: คิดก่อน\nคำตอบ: 42', false), { main: '\nคำตอบ: 42', thinks: ['Thinking Process: คิดก่อน'], partial: null })
check('non-verbal text untouched', parseThinks('Just a normal answer', false), { main: 'Just a normal answer', thinks: [], partial: null })
check('verbal multiple lines until answer', parseThinks('Thinking Process: line1\nline2\nline3\nAnswer: 7', false), { main: '\nAnswer: 7', thinks: ['Thinking Process: line1\nline2\nline3'], partial: null })
// XML tags must take precedence over the verbal fallback when both are
// present (the verbal scanner would otherwise swallow the whole message).
check('xml beats verbal fallback', parseThinks(X_OPEN + '\nthink here\n' + X_CLOSE + '\nThinking Process: not verbal\nAnswer: 42', false), { main: '\nThinking Process: not verbal\nAnswer: 42', thinks: ['\nthink here\n'], partial: null })
// Verbal-leading message that ALSO contains a real <think> block: the
// verbal preamble wins (verbal-first ordering — see parseThinks comment),
// so the whole opening section becomes ONE think block. The stored body is
// the NORMALISED form (tags converted to internal markers) because
// normalisation runs before the verbal scan.
check('verbal-leading + xml block stays verbal-first', parseThinks('Thinking Process: preamble\n' + X_OPEN + '\nreal tag think\n' + X_CLOSE + '\nAnswer: 42', false), { main: '\nAnswer: 42', thinks: ['Thinking Process: preamble\n thinking\nreal tag think\n response'], partial: null })
// Case-insensitive normalisation: <Think> / <THINK> are the same tag.
check('xml uppercase <Think> normalized', parseThinks('Hello <Think> cap </Think> world', false), { main: 'Hello  world', thinks: [' cap '], partial: null })
check('xml all-caps <THINK> normalized', parseThinks(X_OPEN.toUpperCase() + ' caps ' + X_CLOSE.toUpperCase() + ' tail', false), { main: ' tail', thinks: [' caps '], partial: null })
// A <think> glued to a word (mid-word, e.g. "x<think>y") is NOT a block
// opener — the normaliser requires line-start or preceding whitespace, so
// only genuine tag positions convert (parity with legacy SPA which split
// on every <think>; the whitespace guard is strictly more conservative).
check('literal <think> mid-word untouched', parseThinks('x<think>y', false), { main: 'x<think>y', thinks: [], partial: null })

console.log('')
console.log(pass + ' passed, ' + fail + ' failed')
process.exit(fail > 0 ? 1 : 0)
