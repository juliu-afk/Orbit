<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiGet, apiPut } from '@/services/api'
import { ElMessage } from 'element-plus'

const props = defineProps<{ section: string }>()

const content = ref('')
const saving = ref(false)
const loadedSection = ref('')

watch(() => props.section, async (sec) => {
  if (!sec) return
  await loadContent(sec)
})

async function loadContent(sec: string) {
  try {
    const data = await apiGet<Record<string, unknown>>(`/api/v1/config/${sec}`)
    // 后端返回 YAML dict 的 JSON 表示，转回 YAML 字符串展示
    content.value = data ? yamlStringify(data) : ''
    loadedSection.value = sec
  } catch {
    content.value = ''
  }
}

async function save() {
  if (!props.section) return
  saving.value = true
  try {
    await apiPut(`/api/v1/config/${props.section}`, {
      content: content.value,
      author: 'ui',
    })
    ElMessage.success('保存成功')
  } catch {
    ElMessage.error('保存失败')
  }
  saving.value = false
}

// 简单 YAML 序列化——零依赖，覆盖常见深度
function yamlStringify(obj: Record<string, unknown>, indent = 0): string {
  const pad = '  '.repeat(indent)
  return Object.entries(obj).map(([k, v]) => {
    if (v === null || v === undefined) return `${pad}${k}: null`
    if (typeof v === 'object' && !Array.isArray(v)) {
      return `${pad}${k}:\n${yamlStringify(v as Record<string, unknown>, indent + 1)}`
    }
    if (Array.isArray(v)) {
      if (v.length === 0) return `${pad}${k}: []`
      return `${pad}${k}:\n${v.map(item => `${pad}  - ${item}`).join('\n')}`
    }
    return `${pad}${k}: ${v}`
  }).join('\n')
}
</script>

<template>
<div>
  <el-input
    v-model="content" type="textarea" :rows="18"
    placeholder="加载中..."
    style="font-family:var(--font-mono);font-size:12px"
    :disabled="!loadedSection"
  />
  <div style="margin-top:12px">
    <el-button type="primary" size="small" @click="save" :loading="saving" :disabled="!loadedSection">
      保存
    </el-button>
  </div>
</div>
</template>
