/* thinking-block extraction (port of legacy SPA behavior):
   - completed  thinking… response blocks → collapsed accordions
   - an open ` thinking` during streaming → live open accordion
   - partial tag tails ("<thi", "</th") are HELD BACK so raw tag fragments
     never flash on screen mid-stream.
   - XML `<think>`…`</think>` tags (Qwen3 / DeepSeek / R1 chat templates)
     are normalised to the internal markers so reasoning models render as
     accordions too — legacy SPA already did this via applySegmentedContent.
   - verbal/prose thinking fallback (port of main SPA): models trained
     without think tags (e.g. Kimi/Qwen instruction fine-tunes) open
     with a preamble like "Thinking Process:" — detected at the start of
     an assistant message; the block ends at the first answer separator. */

export interface ThinkParse {
  main: string
  thinks: string[]
  /** content of a still-open  thinking block while streaming (null = none) */
  partial: string | null
}

/** The exact markers the server emits. Single source of truth — the marker
    strings and their lengths drifted apart once (magic +7/+8 leaked
    "ng"/"se" into block content); everything derives from these. */
const OPEN_TAG = ' thinking'
const CLOSE_TAG = ' response'
const OPEN_LEN = OPEN_TAG.length // 9
const CLOSE_LEN = CLOSE_TAG.length // 9

/** XML thinking tags emitted by Qwen3/DeepSeek-family chat templates
    (e.g. `\n<think>…</think>\n`). Normalised to the internal markers
    below so the tag scanner stays a single code path. */
const XML_OPEN = '<think>'
const XML_CLOSE = '</think>'

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

/** hold back a trailing fragment that is a prefix of the internal
    markers OR the XML tags (`<thi`, `</th`, ` thinki`, ` respons`…).
    The XML prefixes matter because the normaliser only fires on the
    COMPLETE tag — an in-flight `<think>` must not flash raw. */
function splitTagTail(s: string): [string, string] {
  const m = s.match(/<\/?[a-zA-Z]*$/)
  if (!m) return [s, '']
  const tail = m[0].toLowerCase()
  if (
    OPEN_TAG.startsWith(tail) ||
    CLOSE_TAG.startsWith(tail) ||
    XML_OPEN.startsWith(tail) ||
    XML_CLOSE.startsWith(tail)
  ) {
    return [s.slice(0, s.length - m[0].length), m[0]]
  }
  return [s, '']
}

/**
 * Normalise XML thinking tags (`<think>`…`</think>`, case-insensitive) to
 * the internal markers. Only tags at line-start or after whitespace are
 * converted (`/(?:^|\s)<think>/i`), so a literal "<think>" inside prose
 * (e.g. a model explaining the tag) is NOT mis-read as a block opener.
 */
function normalizeXmlTags(raw: string): string {
  return raw
    .replace(/(^|\s)<think>/gi, (_m, pre) => pre + OPEN_TAG)
    .replace(/(^|\s)<\/think>/gi, (_m, pre) => pre + CLOSE_TAG)
}

/**
 * Scan internal markers (` thinking`…` response`) into blocks.
 * Returns a full ThinkParse — caller decides whether tags were present.
 */
function scanTagBlocks(src: string, streaming: boolean): ThinkParse {
  // Tag scanning ONLY — the verbal fallback lives in parseThinks so that
  // real tags always take precedence over a prose preamble.
  const thinks: string[] = []
  let main = ''
  let partial: string | null = null
  let i = 0

  for (;;) {
    // Match ` thinking` after a space, scanning forward from `i` so an
    // earlier block is never re-found (a full-string search here would
    // loop forever on the first block). Leading ` thinking` at position 0
    // has NO preceding space (the server emits it at the start of the
    // message) — match it explicitly.
    const open =
      i === 0 && src.startsWith(OPEN_TAG)
        ? 0
        : src.indexOf(OPEN_TAG, i)
    if (open === -1) {
      main += src.slice(i)
      break
    }
    main += src.slice(i, open)
    const close = src.indexOf(CLOSE_TAG, open + OPEN_LEN)
    if (close === -1) {
      if (streaming) {
        partial = src.slice(open + OPEN_LEN)
      } else {
        // finished with an unclosed block — treat the rest as thinking
        thinks.push(src.slice(open + OPEN_LEN))
      }
      break
    }
    thinks.push(src.slice(open + OPEN_LEN, close))
    i = close + CLOSE_LEN
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

export function parseThinks(raw: string, streaming: boolean): ThinkParse {
  // Normalise XML thinking tags to the internal markers FIRST, so the
  // scanner (and the leading-tag + partial-tail logic) is one path.
  const src = normalizeXmlTags(raw)

  // Verbal/prose fallback first. This ordering is intentional: a prose
  // preamble ("Thinking Process:") must be detected before the tag
  // scanner, because the scanner would otherwise mis-read the ordinary
  // word "thinking" inside prose ("still thinking…") as a marker.
  // XML precedence is unaffected: a normalized leading ` thinking`
  // (from `<think>`) does not match THINK_VERBAL_RE (which requires
  // "thinking process"/"chain of thought"/"reasoning" as a word), so
  // tag-based blocks still win when the message OPENS with a tag.
  const verbal = extractVerbalThink(src)
  if (verbal) {
    const [thinkBody, rest] = verbal
    if (rest === '' && streaming) {
      return { main: '', thinks: [], partial: thinkBody }
    }
    if (rest === '') {
      return { main: '', thinks: [thinkBody], partial: null }
    }
    return { main: rest, thinks: [thinkBody], partial: null }
  }

  return scanTagBlocks(src, streaming)
}