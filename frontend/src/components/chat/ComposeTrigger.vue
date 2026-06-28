<script setup lang="ts">
/** Compose 编排触发组件——粘贴 spec YAML 并执行多 Agent 编排。

 * WHY: 后端 POST /api/v1/compose/run 已实现但前端无入口。
 */
import { ref } from 'vue'

const emit = defineEmits<{
  (e: 'done', result: Record<string, unknown>): void
}>()

const visible = ref(false)
const specYaml = ref('')
const running = ref(false)
const result = ref<string | null>(null)
const error = ref<string | null>(null)

async function triggerCompose() {
  if (!specYaml.value.trim()) return
  running.value = true
  error.value = null
  result.value = null
  try {
    const resp = await fetch(`${window.location.origin}/api/v1/compose/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec: specYaml.value }),
    })
    const body = await resp.json()
    if (body.code === 0) {
      result.value = JSON.stringify(body.data, null, 2)
      emit('done', body.data)
    } else {
      error.value = body.message || 'Compose 执行失败'
    }
  } catch (e) {
    error.value = `请求失败: ${String(e)}`
  } finally {
    running.value = false
  }
}

defineExpose({ open: () => { visible.value = true } })
</script>

<template>
  <el-dialog v-model="visible" title="Spec Compose" width="560px" :close-on-click-modal="false">
    <el-input
      v-model="specYaml"
      type="textarea"
      :rows="10"
      placeholder="粘贴 spec YAML...&#10;&#10;title: 实现登录功能&#10;tasks:&#10;  - id: login&#10;    description: 实现用户名密码登录&#10;    agent_role: developer&#10;    depends_on: []"
    />
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="running" @click="triggerCompose">
        {{ running ? '执行中...' : '编排执行' }}
      </el-button>
    </template>
    <div v-if="result" class="compose-result">
      <pre>{{ result }}</pre>
    </div>
    <div v-if="error" class="compose-error">{{ error }}</div>
  </el-dialog>
</template>

<style scoped>
.compose-result { margin-top: 12px; background: #f5f5f5; padding: 8px; border-radius: 4px; max-height: 300px; overflow: auto; }
.compose-result pre { margin: 0; font-size: 12px; white-space: pre-wrap; }
.compose-error { margin-top: 12px; color: #ff4d4f; font-size: 13px; }
</style>
