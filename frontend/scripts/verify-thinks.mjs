/* Temporary verification for parseThinks verbal fallback (2026-08-03).
   Run: node scripts/verify-thinks.mjs
   Inline copy of the exact parseThinks logic from src/pages/chat/thinks.ts
   to verify the verbal "Thinking Process:" fallback behaves correctly.

   Tag markers are built from char codes to avoid any source-encoding
   ambiguity in the tag strings themselves. */
const THINK_VERBAL_RE = /^\s*(thinking process|chain of thought|let'?s think step by step|reasoning)\b[^\n]*/i
const THINK_VERBAL_END_RE = /\n\s*(?:final answer|answer|conclusion|สรุป|คำตอบ(?:สุดท้าย)?|ตอบ)\s*[:：#]/i

// Build ' thinking' and ' response' from char codes so both the script and
// the parser agree on identical bytes regardless of file encoding.
const TAG_OPEN = String.fromCharCode(32) + 'thinking'
const TAG_CLOSE = String.fromCharCode(32) + 'response'

function extractVerbalThink(src) {
  const m = src.match(THINK_VERBAL_RE)
  if (!m) return null
  const end = src.search(THINK_VERBAL_END_RE)
  if (end === -1) return [src, '']
  return [src.slice(0, end), src.slice(end)]
}

function splitTagTail(s) {
  const m = s.match(/<\/?[a-zA-Z]*$/)
  if (!m) return [s, '']
  const tail = m[0].toLowerCase()
  if (TAG_OPEN.startsWith(tail) || TAG_CLOSE.startsWith(tail)) {
    return [s.slice(0, s.length - m[0].length), m[0]]
  }
  return [s, '']
}

function parseThinks(src, streaming) {
  const thinks = []
  let main = ''
  let partial = null
  let i = 0

  const verbal = extractVerbalThink(src)
  if (verbal) {
    const [thinkBody, rest] = verbal
    if (rest === '' && streaming) partial = thinkBody
    else if (rest === '') thinks.push(thinkBody)
    else { thinks.push(thinkBody); main = rest }
    return { main, thinks, partial }
  }

  for (;;) {
    const open = src.indexOf(TAG_OPEN, i)
    if (open === -1) { main += src.slice(i); break }
    main += src.slice(i, open)
    const close = src.indexOf(TAG_CLOSE, open + TAG_OPEN.length)
    if (close === -1) {
      if (streaming) partial = src.slice(open + TAG_OPEN.length)
      else thinks.push(src.slice(open + TAG_OPEN.length))
      break
    }
    thinks.push(src.slice(open + TAG_OPEN.length, close))
    i = close + TAG_CLOSE.length
  }

  if (streaming) {
    if (partial !== null) {
      const [body] = splitTagTail(partial)
      partial = body
    } else {
      const [body, tail] = splitTagTail(main)
      if (tail) { main = body; partial = '' }
    }
  }
  return { main, thinks, partial }
}

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

console.log('=== verbal "Thinking Process:" fallback ===')
check('verbal completed with answer', parseThinks('Thinking Process: let me reason\nFinal answer: 42', false), { main: '\nFinal answer: 42', thinks: ['Thinking Process: let me reason'], partial: null })
check('verbal streaming (no separator yet)', parseThinks('Thinking Process: still thinking...', true), { main: '', thinks: [], partial: 'Thinking Process: still thinking...' })
check('verbal completed no separator', parseThinks('Thinking Process: all thinking', false), { main: '', thinks: ['Thinking Process: all thinking'], partial: null })
check('verbal Thai separator', parseThinks('Thinking Process: คิดก่อน\nคำตอบ: 42', false), { main: '\nคำตอบ: 42', thinks: ['Thinking Process: คิดก่อน'], partial: null })
check('non-verbal text untouched', parseThinks('Just a normal answer', false), { main: 'Just a normal answer', thinks: [], partial: null })
check('verbal multiple lines until answer', parseThinks('Thinking Process: line1\nline2\nline3\nAnswer: 7', false), { main: '\nAnswer: 7', thinks: ['Thinking Process: line1\nline2\nline3'], partial: null })

console.log('')
console.log(pass + ' passed, ' + fail + ' failed')
process.exit(fail > 0 ? 1 : 0)