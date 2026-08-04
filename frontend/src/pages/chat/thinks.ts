/* ` thinking` block extraction (port of legacy SPA behavior):
   - completed  thinking… response blocks → collapsed accordions
   - an open ` thinking` during streaming → live open accordion
   - partial tag tails ("<thi", "</th") are HELD BACK so raw tag fragments
     never flash on screen mid-stream.
   - verbal/prose thinking fallback (port of main SPA): models trained
     without  think  tags (e.g. Kimi/Qwen instruction fine-tunes) open
     with a preamble like "Thinking Process:" — detected at the start of
     an assistant message; the block ends at the first answer separator. */

export interface ThinkParse {
  main: string
  thinks: string[]
  /** content of a still-open  thinking block while streaming (null = none) */
  partial: string | null
}

/** Verbal thinking preamble (port of main SPA THINK_VERBAL_RE) */
const THINK_VERBAL_RE = /^\s*(thinking process|chain of thought|let'?s think step by step|reasoning)\b[^\n]*/i
/** Answer separator that ends a verbal thinking block (THINK_VERBAL_END_RE) */
const THINK_VERBAL_END_RE = /\n\s*(?:final answer|answer|conclusion|สรุป|คำตอบ(?:สุดท้าย)?|ตอบ)\s*[:：#]/i

/**
 * Extract a verbal "Thinking Process:" block from the very start of an
 * assistant message. Returns [thinking, rest] or null when the message
 * does not open with a recognized prose preamble.
 */
function extractVerbalThink(src: string): [string, string] | null {
  const m = src.match(THINK_VERBAL_RE)
  if (!m) return null
  const end = src.search(THINK_VERBAL_END_RE)
  if (end === -1) {
    // No answer separator yet — treat the whole message as thinking while
    // streaming; on completion the whole message is thinking.
    return [src, '']
  }
  return [src.slice(0, end), src.slice(end)]
}

/** hold back a trailing fragment that is a prefix of  thinking /  response */
function splitTagTail(s: string): [string, string] {
  const m = s.match(/<\/?[a-zA-Z]*$/)
  if (!m) return [s, '']
  const tail = m[0].toLowerCase()
  if (' thinking'.startsWith(tail) || ' response'.startsWith(tail)) {
    return [s.slice(0, s.length - m[0].length), m[0]]
  }
  return [s, '']
}

export function parseThinks(src: string, streaming: boolean): ThinkParse {
  const thinks: string[] = []
  let main = ''
  let partial: string | null = null
  let i = 0

  // Verbal/prose fallback first: only when the message opens with a
  // recognized preamble (e.g. "Thinking Process:"). Tag-based blocks
  // below take precedence when both are present.
  const verbal = extractVerbalThink(src)
  if (verbal) {
    const [thinkBody, rest] = verbal
    if (rest === '' && streaming) {
      partial = thinkBody
    } else if (rest === '') {
      thinks.push(thinkBody)
    } else {
      thinks.push(thinkBody)
      main = rest
    }
    return { main, thinks, partial }
  }

  for (;;) {
    const open = src.indexOf(' thinking', i)
    if (open === -1) {
      main += src.slice(i)
      break
    }
    main += src.slice(i, open)
    const close = src.indexOf(' response', open + 7)
    if (close === -1) {
      if (streaming) {
        partial = src.slice(open + 7)
      } else {
        // finished with an unclosed block — treat the rest as thinking
        thinks.push(src.slice(open + 7))
      }
      break
    }
    thinks.push(src.slice(open + 7, close))
    i = close + 8
  }

  if (streaming) {
    if (partial !== null) {
      const [body] = splitTagTail(partial)
      partial = body
    } else {
      const [body, tail] = splitTagTail(main)
      if (tail) {
        main = body
        partial = '' // an opener is forming; show the live block empty
      }
    }
  }

  return { main, thinks, partial }
}