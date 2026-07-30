/* `<think>` block extraction (port of legacy SPA behavior):
   - completed <think>…</think> blocks → collapsed accordions
   - an open `<think>` during streaming → live open accordion
   - partial tag tails ("<thi", "</th") are HELD BACK so raw tag fragments
     never flash on screen mid-stream. */

export interface ThinkParse {
  main: string
  thinks: string[]
  /** content of a still-open <think> block while streaming (null = none) */
  partial: string | null
}

/** hold back a trailing fragment that is a prefix of <think> / </think> */
function splitTagTail(s: string): [string, string] {
  const m = s.match(/<\/?[a-zA-Z]*$/)
  if (!m) return [s, '']
  const tail = m[0].toLowerCase()
  if ('<think>'.startsWith(tail) || '</think>'.startsWith(tail)) {
    return [s.slice(0, s.length - m[0].length), m[0]]
  }
  return [s, '']
}

export function parseThinks(src: string, streaming: boolean): ThinkParse {
  const thinks: string[] = []
  let main = ''
  let partial: string | null = null
  let i = 0

  for (;;) {
    const open = src.indexOf('<think>', i)
    if (open === -1) {
      main += src.slice(i)
      break
    }
    main += src.slice(i, open)
    const close = src.indexOf('</think>', open + 7)
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
