<!-- NewSessionDialog.vue: 新建 Session 弹窗——打开已有 / 新建项目 二选一 -->
<template>
  <el-dialog
    v-model="visible"
    title="新建会话"
    width="500px"
    :close-on-click-modal="false"
  >
    <el-radio-group v-model="mode" class="mode-switch">
      <el-radio-button value="open">打开已有项目</el-radio-button>
      <el-radio-button value="create">新建项目</el-radio-button>
    </el-radio-group>

    <!-- Tab A: 打开已有项目 -->
    <div v-if="mode === 'open'" class="tab-content">
      <!-- 已注册项目列表 -->
      <div v-if="existingProjects.length > 0" class="project-list-section">
        <p class="section-label">已注册项目</p>
        <div
          v-for="p in existingProjects"
          :key="p.name"
          class="project-list-item"
          :class="{ selected: selectedProject === p.name }"
          @click="selectProject(p)"
        >
          <span class="pli-name">📁 {{ p.name }}</span>
          <span class="pli-path">{{ p.local_path || p.path || '' }}</span>
        </div>
      </div>
      <p v-else class="hint">暂无已注册项目——请手动输入路径或新建项目</p>

      <!-- 手动输入路径 -->
      <el-divider v-if="existingProjects.length > 0">或手动输入路径</el-divider>
      <el-input
        v-model="openPath"
        placeholder="粘贴项目文件夹路径，如 D:/Code-Insight-Financial"
        clearable
      >
        <template #prefix>
          <span style="color:#888;font-size:12px">📁</span>
        </template>
      </el-input>
      <p class="hint">
        在文件管理器中右键文件夹 →「复制为路径」→ 粘贴到此处
      </p>
      <p v-if="pathError" class="error">{{ pathError }}</p>
    </div>

    <!-- Tab B: 新建项目 -->
    <div v-if="mode === 'create'" class="tab-content">
      <el-input
        v-model="newProjectName"
        placeholder="项目名称（文件夹名）"
        clearable
        class="mb-8"
      />
      <el-input
        v-model="newParentDir"
        placeholder="父目录路径，如 D:/Projects"
        clearable
      />
      <p class="hint">
        将在父目录下创建以项目名称命名的文件夹。
      </p>
      <p v-if="createError" class="error">{{ createError }}</p>
    </div>

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleConfirm">
        确认
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useSessionStore } from '@/stores/session'

interface ProjectItem {
  name: string
  local_path?: string
  path?: string
  repo_url?: string
}

const visible = defineModel<boolean>('visible', { default: false })
const emit = defineEmits<{
  'confirmed': []
}>()

const session = useSessionStore()
const mode = ref<'open' | 'create'>('open')
const openPath = ref('')
const newProjectName = ref('')
const newParentDir = ref('')
const pathError = ref('')
const createError = ref('')
const submitting = ref(false)
const existingProjects = ref<ProjectItem[]>([])
const selectedProject = ref('')

// WHY 弹窗打开时自动拉取已注册项目列表：替代手动输入路径
watch(visible, async (v) => {
  if (v) {
    try {
      const r = await fetch('/api/v1/projects')
      const j = await r.json()
      if (j.code === 0 && Array.isArray(j.data)) {
        existingProjects.value = j.data
      }
    } catch { /* fetch 失败静默回退到手动输入 */ }
  }
})

function selectProject(p: ProjectItem) {
  selectedProject.value = p.name
  openPath.value = p.local_path || p.path || ''
}

// WHY 前端即时校验: 减少无效 API 请求，提升 UX
const ILLEGAL_CHARS = /[<>"|?*]/

function validatePath(path: string): string {
  if (!path.trim()) return '路径不能为空'
  if (ILLEGAL_CHARS.test(path)) return '路径含非法字符（< > " | ? *）'
  return ''
}

async function handleConfirm() {
  submitting.value = true
  pathError.value = ''
  createError.value = ''

  try {
    if (mode.value === 'open') {
      const err = validatePath(openPath.value)
      if (err) { pathError.value = err; return }

      // 从路径提取项目名（文件夹名）
      const parts = openPath.value.replace(/\\/g, '/').replace(/\/$/, '').split('/')
      const projectName = parts[parts.length - 1]

      // 注册项目
      const r = await fetch('/api/v1/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: projectName, local_path: openPath.value.trim() }),
      })
      const j = await r.json()
      if (j.code !== 0) {
        pathError.value = j.message || '注册项目失败'
        return
      }

      // 创建 Session
      await session.createSession(projectName)
    } else {
      if (!newProjectName.value.trim()) { createError.value = '项目名称不能为空'; return }
      const nameErr = validatePath(newProjectName.value)
      if (nameErr) { createError.value = '项目名称' + nameErr; return }
      if (!newParentDir.value.trim()) { createError.value = '父目录路径不能为空'; return }
      const dirErr = validatePath(newParentDir.value)
      if (dirErr) { createError.value = dirErr; return }

      const projectName = newProjectName.value.trim()
      const parentDir = newParentDir.value.trim().replace(/\\/g, '/').replace(/\/$/, '')

      // 注册项目（后端不会自动创建文件夹——MVP 阶段用户手动创建或后端 os.makedirs）
      const r = await fetch('/api/v1/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: projectName, local_path: `${parentDir}/${projectName}` }),
      })
      const j = await r.json()
      if (j.code !== 0) {
        createError.value = j.message || '注册项目失败'
        return
      }

      await session.createSession(projectName)
    }

    emit('confirmed')
    visible.value = false
    resetForm()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '未知错误'
    if (mode.value === 'open') pathError.value = msg
    else createError.value = msg
  } finally {
    submitting.value = false
  }
}

function handleCancel() {
  visible.value = false
  resetForm()
}

function resetForm() {
  openPath.value = ''
  newProjectName.value = ''
  newParentDir.value = ''
  pathError.value = ''
  createError.value = ''
}
</script>

<style scoped>
.mode-switch { margin-bottom: 16px; display: block; }
.tab-content { padding-top: 12px; }
.tab-content .el-input { width: 100%; }
.mb-8 { margin-bottom: 8px; }
.hint { font-size: 12px; color: #888; margin-top: 6px; }
.error { font-size: 12px; color: #f44336; margin-top: 6px; }
.section-label { font-size: 12px; color: #888; margin-bottom: 8px; }
.project-list-section { margin-bottom: 12px; }
.project-list-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 10px; border-radius: 4px; cursor: pointer;
  border: 1px solid #2a2a4a; margin-bottom: 4px;
  transition: background 0.15s;
}
.project-list-item:hover { background: rgba(76, 175, 80, 0.08); }
.project-list-item.selected { border-color: #4caf50; background: rgba(76, 175, 80, 0.12); }
.pli-name { font-size: 13px; font-weight: 500; color: #e0e0e0; }
.pli-path { font-size: 11px; color: #666; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
