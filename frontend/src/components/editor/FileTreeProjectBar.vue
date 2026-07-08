<!-- FileTreeProjectBar.vue: FileTree 顶部项目选择器——下拉+注册新项目 -->
<template>
  <div class="ft-project-bar">
    <el-dropdown
      trigger="click"
      class="ft-dropdown"
      @command="onCommand"
      @visible-change="onVisibleChange"
    >
      <span class="ft-trigger">
        <span class="ft-icon">📁</span>
        <span class="ft-label">{{ displayName }}</span>
        <span class="ft-arrow">▾</span>
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="p in projects"
            :key="p.name"
            :command="p.name"
            :class="{ 'is-active': currentProjectName === p.name }"
          >
            <span class="dd-name">{{ p.name }}</span>
            <span class="dd-path">{{ p.local_path || p.path || '' }}</span>
          </el-dropdown-item>
          <el-dropdown-item v-if="projects.length === 0" disabled>
            暂无已注册项目
          </el-dropdown-item>
          <el-dropdown-item divided command="__new__" class="dd-new">
            ➕ 注册新项目
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- 注册新项目弹窗 -->
    <el-dialog v-model="showNewDialog" title="注册新项目" width="360px" :close-on-click-modal="true" append-to-body>
      <el-input v-model="newName" placeholder="项目名称（文件夹名）" class="mb-8" />
      <el-input v-model="newParentDir" placeholder="父目录路径，如 D:/Projects" />
      <p class="hint">将在父目录下自动创建项目文件夹并注册。</p>
      <p v-if="newError" class="error">{{ newError }}</p>
      <template #footer>
        <el-button @click="showNewDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface ProjectItem {
  name: string
  local_path?: string
  path?: string
}

const props = defineProps<{
  currentPath: string
}>()

const emit = defineEmits<{
  'change-project': [path: string]
  'create-project': [projectName: string]
}>()

const projects = ref<ProjectItem[]>([])
const fetched = ref(false)
const showNewDialog = ref(false)
const newName = ref('')
const newParentDir = ref('')
const newError = ref('')
const submitting = ref(false)

const currentProjectName = computed(() => {
  if (!props.currentPath) return ''
  const parts = props.currentPath.replace(/\\/g, '/').replace(/\/$/, '').split('/')
  return parts[parts.length - 1] || ''
})

const displayName = computed(() => currentProjectName.value || '选择项目...')

function onVisibleChange(visible: boolean) {
  if (visible && !fetched.value) {
    fetched.value = true
    fetch('/api/v1/projects')
      .then(r => r.json())
      .then(j => {
        if (j.code === 0 && Array.isArray(j.data)) projects.value = j.data
      })
      .catch(() => {})
  }
}

function onCommand(cmd: string) {
  if (cmd === '__new__') {
    showNewDialog.value = true
    return
  }
  const p = projects.value.find(x => x.name === cmd)
  if (p?.local_path) {
    emit('change-project', p.local_path)
  }
}

const ILLEGAL_CHARS = /[<>"|?*]/

async function handleCreate() {
  submitting.value = true; newError.value = ''
  try {
    const name = newName.value.trim()
    const parentDir = newParentDir.value.trim().replace(/\\/g, '/').replace(/\/$/, '')
    if (!name) { newError.value = '项目名称不能为空'; return }
    if (ILLEGAL_CHARS.test(name)) { newError.value = '项目名称含非法字符'; return }
    if (!parentDir) { newError.value = '父目录路径不能为空'; return }
    const fullPath = `${parentDir}/${name}`

    // 注册项目（后端 os.makedirs 自动创建文件夹）
    const r = await fetch('/api/v1/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, local_path: fullPath }),
    })
    const j = await r.json()
    if (j.code !== 0) { newError.value = j.message || j.detail?.detail || '注册失败'; return }

    // 刷新项目列表
    projects.value.push({ name, local_path: fullPath })
    showNewDialog.value = false
    newName.value = ''; newParentDir.value = ''

    // 切换 FileTree 到新项目 + 通知父级创建会话
    emit('change-project', fullPath)
    emit('create-project', name)
  } catch (e: unknown) {
    newError.value = e instanceof Error ? e.message : '未知错误'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.ft-project-bar { padding: 4px 8px; border-bottom: 1px solid var(--color-orbit-border); }
.ft-dropdown { display: block; width: 100%; }
.ft-trigger {
  display: flex; align-items: center; gap: 4px;
  width: 100%; padding: 4px 8px;
  background: rgba(255,255,255,0.04); border: 1px solid transparent;
  border-radius: 4px; color: var(--color-orbit-text-secondary);
  font-family: var(--font-mono); font-size: 11px;
  cursor: pointer; box-sizing: border-box;
  transition: background 0.15s, border-color 0.15s;
}
.ft-trigger:hover { background: rgba(255,255,255,0.08); border-color: var(--color-orbit-border); color: var(--color-orbit-text); }
.ft-icon { flex-shrink: 0; font-size: 12px; }
.ft-label { flex: 1; text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ft-arrow { font-size: 8px; color: var(--color-orbit-text-muted); flex-shrink: 0; }

.dd-name { font-size: 12px; font-weight: 500; color: #e0e0e0; }
.dd-path { display: block; font-size: 10px; color: #666; margin-top: 1px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.is-active .dd-name { color: var(--color-orbit-accent); }
.dd-new .dd-name { color: var(--color-orbit-accent); }

.mb-8 { margin-bottom: 8px; }
.hint { font-size: 12px; color: #888; margin-top: 6px; }
.error { font-size: 12px; color: #f44336; margin-top: 6px; }
</style>
