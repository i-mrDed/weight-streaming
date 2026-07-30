// Self-hosted fonts — NO CDN at runtime (local-first product, spec risk row)
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import '@fontsource-variable/noto-sans-thai'

// Themes + base tokens (registry imports its CSS)
import { App } from './app'
import { render } from 'preact'

// Structural styles (reference semantic tokens only)
import './styles/components.css'
import './styles/shell.css'
import './styles/pages.css'

const root = document.getElementById('app')!
root.innerHTML = '' // clear boot-root placeholder
render(<App />, root)
