/** MCP Store——管理外部 MCP 服务器连接与工具发现。
 *
 * 对应后端 /api/v1/mcp/* 路由。
 * 后端未实现时静默降级（服务器列表为空）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface McpServer {
  name: string
  command: string
  args: string[]
  enabled: boolean
  status: 'connected' | 'disabled' | 'error'
  tools_count: number
  error_message?: string
}

export interface McpTool {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

const BASE = '/api/v1/mcp'

export const useMcpStore = defineStore('mcp', () => {
  const servers = ref<McpServer[]>([])
  const tools = ref<Record<string, McpTool[]>>({})
  const loading = ref(false)
  const error = ref('')

  async function fetchServers() {
    loading.value = true
    error.value = ''
    try {
      const r = await fetch(`${BASE}/servers`)
      const j = await r.json()
      if (j.code === 0) {
        servers.value = j.data as McpServer[]
      }
    } catch {
      error.value = '后端 MCP 路由未就绪，请确认后端已启动并配置 MCP 服务器'
      servers.value = []
    } finally {
      loading.value = false
    }
  }

  async function toggleServer(name: string, enabled: boolean) {
    try {
      await fetch(`${BASE}/servers/${name}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      const s = servers.value.find(s => s.name === name)
      if (s) s.enabled = enabled
    } catch {
      error.value = `切换服务器 ${name} 失败`
    }
  }

  async function fetchTools(serverName: string) {
    try {
      const r = await fetch(`${BASE}/servers/${serverName}/tools`)
      const j = await r.json()
      if (j.code === 0) {
        tools.value[serverName] = j.data as McpTool[]
      }
    } catch {
      tools.value[serverName] = tools.value[serverName] || []
    }
  }

  async function discoverTools(serverName: string) {
    try {
      await fetch(`${BASE}/servers/${serverName}/discover`, { method: 'POST' })
      await fetchTools(serverName)
    } catch {
      error.value = `发现工具失败: ${serverName}`
    }
  }

  function reset() {
    servers.value = []
    tools.value = {}
    error.value = ''
  }

  return {
    servers, tools, loading, error,
    fetchServers, toggleServer, fetchTools, discoverTools, reset,
  }
})
