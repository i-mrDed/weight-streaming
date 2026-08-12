/* Agent & Workspace (AGENT_TOOLS_PLAN.md) — enable the chat agent loop and
   pick the workspace root the built-in tools may read. Uses /v1/agent/*. */
import { useSignal } from '@preact/signals'
import { useEffect } from 'preact/hooks'
import { Card } from '@/components/Card'
import { Button } from '@/components/Button'
import { Tip } from '@/components/Tip'
import { toast } from '@/components/Toast'
import { t } from '@/i18n'
import {
  type AgentConfig,
  type AgentTool,
  getAgentConfig,
  listAgentTools,
  listMCPTools,
  putAgentConfig,
} from '@/core/api'

export function AgentSection() {
  const cfg = useSignal<AgentConfig | null>(null)
  const rootDraft = useSignal('')
  const tools = useSignal<AgentTool[]>([])
  const mcpCount = useSignal(0)
  const loading = useSignal(true)

  async function load() {
    loading.value = true
    try {
      const [c, builtin, mcp] = await Promise.all([
        getAgentConfig(),
        listAgentTools().catch(() => [] as AgentTool[]),
        listMCPTools().catch(() => []),
      ])
      cfg.value = c
      rootDraft.value = c.workspace_root
      tools.value = builtin
      mcpCount.value = mcp.length
    } catch (e) {
      toast('error', String(e))
    } finally {
      loading.value = false
    }
  }
  useEffect(() => {
    void load()
  }, [])

  async function save() {
    try {
      const updated = await putAgentConfig({
        enabled: cfg.value?.enabled ?? true,
        workspace_root: rootDraft.value.trim(),
      })
      cfg.value = updated
      toast('success', t('settings.agent.saved'))
      void load()
    } catch (e) {
      toast('error', String(e))
    }
  }

  return (
    <Card class="set-card">
      <label class="set-row">
        <span>
          <strong>{t('settings.agent.subtitle')}</strong> <Tip label={t('settings.agent.subtitleHint')} />
          <p class="set-note">{t('settings.agent.note')}</p>
        </span>
        <input
          type="checkbox"
          checked={cfg.value?.enabled ?? false}
          onChange={(e) => {
            if (cfg.value) cfg.value = { ...cfg.value, enabled: (e.target as HTMLInputElement).checked }
          }}
        />
      </label>

      <div class="set-row">
        <span>
          <strong>{t('settings.agent.root')}</strong> <Tip label={t('settings.agent.rootHint')} />
        </span>
      </div>
      {loading.value ? (
        <p class="set-note">{t('common.loading')}</p>
      ) : (
        <input
          class="form__input tnum"
          value={rootDraft.value}
          onInput={(e) => (rootDraft.value = (e.target as HTMLInputElement).value)}
          placeholder={t('settings.agent.rootPlaceholder')}
        />
      )}

      <div class="set-row">
        <span>
          <strong>{t('settings.agent.toolsTitle')}</strong>
          <p class="set-note">{t('settings.agent.toolsHint', { builtin: tools.value.length, mcp: mcpCount.value })}</p>
          {tools.value.length > 0 ? (
            <ul class="agent-tools">
              {tools.value.map((x) => (
                <li key={x.name}>
                  <code>{x.name}</code>
                </li>
              ))}
            </ul>
          ) : null}
        </span>
      </div>

      <div class="set-row">
        <Button variant="primary" size="sm" onClick={() => void save()}>
          {t('common.save')}
        </Button>
      </div>
    </Card>
  )
}
