/* Generate raster app icons + favicon.ico from the Streamline W mark.
   Run: npm run gen:icons  (dev-only; outputs committed to public/) */
import sharp from 'sharp'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const pub = join(root, 'public')

// Self-contained tile SVG — dark app tile + gradient mark
const tileSvg = (size) => `
<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#0b0f19"/>
  <defs>
    <linearGradient id="w" x1="6" y1="14" x2="58" y2="52" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#8b5cf6"/><stop offset="0.38" stop-color="#6366f1"/>
      <stop offset="0.72" stop-color="#06b6d4"/><stop offset="1" stop-color="#14b8a6"/>
    </linearGradient>
    <linearGradient id="b" x1="6" y1="14" x2="58" y2="52" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#8b5cf6"/><stop offset="1" stop-color="#6366f1"/>
    </linearGradient>
    <linearGradient id="f" x1="6" y1="14" x2="58" y2="52" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#06b6d4"/><stop offset="1" stop-color="#14b8a6"/>
    </linearGradient>
  </defs>
  <g transform="translate(1.5 1.5) scale(0.953)">
    <path d="M8 16 C11 32 14.5 44 19 50 C23.5 43 28 33 32 26 C36 33 40.5 43 45 50 C49.5 44 53 32 56 16" transform="translate(0 -3.4)" stroke="url(#b)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.48"/>
    <path d="M8 16 C11 32 14.5 44 19 50 C23.5 43 28 33 32 26 C36 33 40.5 43 45 50 C49.5 44 53 32 56 16" stroke="url(#w)" stroke-width="4.4" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M8 16 C11 32 14.5 44 19 50 C23.5 43 28 33 32 26 C36 33 40.5 43 45 50 C49.5 44 53 32 56 16" transform="translate(0 3.4)" stroke="url(#f)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
    <circle cx="58.6" cy="16.4" r="1.5" fill="#14b8a6" opacity="0.65"/>
    <circle cx="61.4" cy="12.6" r="1.15" fill="#14b8a6" opacity="0.45"/>
    <circle cx="63.4" cy="8.6" r="0.85" fill="#14b8a6" opacity="0.3"/>
  </g>
</svg>`

async function png(size, out) {
  await sharp(Buffer.from(tileSvg(size * 4))).resize(size, size).png().toFile(join(pub, out))
  console.log(`✓ ${out} (${size}×${size})`)
}

/** ICO container with PNG-encoded entries (valid per ICO spec, all modern browsers) */
async function ico(sizes, out) {
  const pngs = []
  for (const s of sizes) {
    pngs.push(await sharp(Buffer.from(tileSvg(s * 4))).resize(s, s).png().toBuffer())
  }
  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0) // reserved
  header.writeUInt16LE(1, 2) // type: icon
  header.writeUInt16LE(pngs.length, 4)
  const entries = []
  let offset = 6 + pngs.length * 16
  pngs.forEach((buf, i) => {
    const e = Buffer.alloc(16)
    e.writeUInt8(sizes[i] >= 256 ? 0 : sizes[i], 0)
    e.writeUInt8(sizes[i] >= 256 ? 0 : sizes[i], 1)
    e.writeUInt8(0, 2) // colors
    e.writeUInt8(0, 3) // reserved
    e.writeUInt16LE(1, 4) // planes
    e.writeUInt16LE(32, 6) // bpp
    e.writeUInt32LE(buf.length, 8)
    e.writeUInt32LE(offset, 12)
    offset += buf.length
    entries.push(e)
  })
  writeFileSync(join(pub, out), Buffer.concat([header, ...entries, ...pngs]))
  console.log(`✓ ${out} (${sizes.join('+')})`)
}

await png(180, 'icon-180.png')
await png(512, 'icon-512.png')
await ico([16, 32], 'favicon.ico')
