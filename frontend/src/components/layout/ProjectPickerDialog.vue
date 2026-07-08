<!-- ProjectPickerDialog.vue: 轻量项目选择器——仅选项目，不创建会话 -->
<template>
  <el-dialog
    v-model="visible"
    title="选择项目"
    width="420px"
    :close-on-click-modal="true"
  >
    <div v-if="projects.length > 0" class="project-list">
      <div
        v-for="p in projects"
        :key="p.name"
        class="project-list-item"
        @click="handlePick(p)"
      >
        <span class="pli-name">📁 {{ p.name }}</span>
        <span class="pli-path">{{ p.local_path || p.path || '' }}</span>
      </div>
    </div>
    <el-empty v-else description="暂无已注册项目" :image-size="48" />

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface ProjectItem {
  name: string
  local_path?: string
  path?: string
}

const visible = defineModel<boolean>('visible', { default: false })
const emit = defineEmits<{
  'pick': [projectName: string]
}>()

const projects = ref<ProjectItem[]>([])

// WHY: 弹窗打开时拉取项目列表——按需加载，减少初始请求
watch(visible, async (v) => {
  if (v) {
    try {
      const r = await fetch('/api/v1/projects')
      const j = await r.json()
      if (j.code === 0 && Array.isArray(j.data)) {
        projects.value = j.data
      }
    } catch { /* 静默回退 */ }
  }
})

function handlePick(p: ProjectItem) {
  emit('pick', p.name)
  visible.value = false
}

function handleCancel() {
  visible.value = false
}
</script>

<style scoped>
.project-list { margin-bottom: 8px; }
.project-list-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 12px; border-radius: 6px; cursor: pointer;
  border: 1px solid #2a2a4a; margin-bottom: 6px;
  transition: background 0.15s, border-color 0.15s;
}
.project-list-item:hover { background: rgba(76, 175, 80, 0.08); border-color: #4caf50; }
.pli-name { font-size: 13px; font-weight: 500; color: #e0e0e0; }
.pli-path { font-size: 11px; color: #666; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
