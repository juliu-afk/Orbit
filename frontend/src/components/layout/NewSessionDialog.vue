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
import { ref } from 'vue'
import { useSessionStore } from '@/stores/session'

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
</style>
