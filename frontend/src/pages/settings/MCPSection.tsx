/* MCP servers manager (P7.4) — add/delete/list MCP server configs.
   Local-first (JSON-backed). Uses the /v1/mcp/* API. */
import { useSignal } from '@preact/signals'
import { useEffect } from 'preact/hooks'
import { Card } from '@/components/Card'
import { Button } from '@/components/Button'
import { EmptyState } from '@/components/EmptyState'
import { Dialog } from '@/components/Dialog'
import { toast } from '@/components/Toast'
import { t } from '@/i18n'
import {
  type MCPServer,
  listMCPServers,
  addMCPServer,
  deleteMCPServer,
} from '@/core/api'

export function MCPSection() {
  const servers = useSignal<MCPServer[]>([])
  const loading = useSignal(true)
  const addOpen = useSignal(false)
  const name = useSignal('')
  const transport = useSignal<'stdio' | 'sse'>('stdio')
  const command = useSignal('')
  const args = useSignal('')
  const url = useSignal('')

  async function load() {
    loading.value = true
    try {
      servers.value = await listMCPServers()
    } catch (e) {
      toast('error', String(e))
    } finally {
      loading.value = false
    }
  }
  useEffect(() => { load() }, [])

  async function save() {
    if (!name.value.trim()) { toast('error', t('settings.mcp.nameRequired')); return }
    try {
      await addMCPServer({
        name: name.value,
        transport: transport.value,
        command: transport.value === 'stdio' ? command.value || undefined : undefined,
        args: transport.value === 'stdio' ? args.value.split(/\s+/).filter(Boolean) : [],
        url: transport.value === 'sse' ? url.value || undefined : undefined,
      })
      toast('success', t('settings.mcp.added'))
      addOpen.value = false
      name.value = ''; command.value = ''; args.value = ''; url.value = ''
      await load()
    } catch (e) {
      toast('error', String(e))
    }
  }

  async function remove(s: MCPServer) {
    try {
      await deleteMCPServer(s.id)
      toast('success', t('settings.mcp.deleted'))
      await load()
    } catch (e) {
      toast('error', String(e))
    }
  }

  return (
    <Card class="set-card">
      <div class="set-row">
        <span>
          <strong>{t('settings.mcp.subtitle')}</strong>
          <p class="set-note">{t('settings.mcp.note')}</p>
        </span>
        <Button size="sm" variant="primary" onClick={() => (addOpen.value = true)}>{t('settings.mcp.add')}</Button>
      </div>

      {loading.value ? (
        <p class="set-note">{t('common.loading')}</p>
      ) : servers.value.length === 0 ? (
        <EmptyState emoji="🔌" title={t('settings.mcp.empty')} />
      ) : (
        <div class="mcp-list">
          {servers.value.map((s) => (
            <div key={s.id} class="mcp-item">
              <div class="mcp-item__info">
                <span class="mcp-item__name">
                  {s.name}
                  <span class={`tag ${s.enabled ? 'tag-green' : 'tag-red'}`}>
                    {s.enabled ? t('settings.mcp.enabled') : t('settings.mcp.disabled')}
                  </span>
                </span>
                <code class="mcp-item__cmd">{s.transport === 'stdio' ? s.command : s.url}</code>
              </div>
              <Button size="sm" variant="danger" onClick={() => remove(s)}>{t('common.delete')}</Button>
            </div>
          ))}
        </div>
      )}

      <Dialog open={addOpen.value} title={t('settings.mcp.add')} onClose={() => (addOpen.value = false)}>
        <div class="form">
          <label class="form__label">{t('settings.mcp.name')}</label>
          <input class="form__input tnum" value={name.value}
            onInput={(e) => (name.value = (e.target as HTMLInputElement).value)} />
          <label class="form__label">{t('settings.mcp.transport')}</label>
          <select class="form__input tnum" value={transport.value}
            onChange={(e) => (transport.value = (e.target as HTMLSelectElement).value as 'stdio' | 'sse')}>
            <option value="stdio">stdio</option>
            <option value="sse">sse</option>
          </select>
          {transport.value === 'stdio' ? (
            <>
              <label class="form__label">{t('settings.mcp.command')}</label>
              <input class="form__input tnum" placeholder="npx" value={command.value}
                onInput={(e) => (command.value = (e.target as HTMLInputElement).value)} />
              <label class="form__label">{t('settings.mcp.args')}</label>
              <input class="form__input tnum" placeholder="-y @modelcontextprotocol/server-filesystem" value={args.value}
                onInput={(e) => (args.value = (e.target as HTMLInputElement).value)} />
            </>
          ) : (
            <>
              <label class="form__label">{t('settings.mcp.url')}</label>
              <input class="form__input tnum" placeholder="http://localhost:8000/sse" value={url.value}
                onInput={(e) => (url.value = (e.target as HTMLInputElement).value)} />
            </>
          )}
          <div class="form__actions">
            <Button onClick={() => (addOpen.value = false)}>{t('common.cancel')}</Button>
            <Button variant="primary" onClick={save}>{t('common.save')}</Button>
          </div>
        </div>
      </Dialog>
    </Card>
  )
}