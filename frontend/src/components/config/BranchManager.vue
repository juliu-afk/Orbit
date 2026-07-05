<script setup lang="ts">
import { ref } from 'vue'
import { apiGet, apiPost, apiPut } from '@/services/api'
import { ElMessage, ElMessageBox } from 'element-plus'

interface GitBranch { name: string; is_current: boolean; last_commit: string }
interface MergeResult { success: boolean; conflict_files: string[]; message: string }

const props = defineProps<{ branches: GitBranch[]; current: string }>()
const emit = defineEmits<{ (e: 'reload'): void }>()

const newBranchName = ref('')
const mergeFrom = ref('')
const conflictSection = ref('')
const conflictContent = ref('')
const resolvedContent = ref('')

async function createBranch() {
  if (!newBranchName.value) return
  try {
    await apiPost('/api/v1/config/branches', { name: newBranchName.value, from_branch: props.current })
    ElMessage.success(`分支 ${newBranchName.value} 已创建`)
    newBranchName.value = ''
    emit('reload')
  } catch { ElMessage.error('创建失败') }
}

async function switchBranch(name: string) {
  try {
    await ElMessageBox.confirm(`切换到分支 ${name}？`, '切换分支', { type: 'warning' })
    await apiPost(`/api/v1/config/branches/switch?name=${encodeURIComponent(name)}`, {})
    ElMessage.success(`已切换到 ${name}`)
    emit('reload')
  } catch { /* 取消 */ }
}

async function mergeBranch() {
  if (!mergeFrom.value) return
  try {
    await ElMessageBox.confirm(`合并 ${mergeFrom.value} → ${props.current}？`, '确认合并')
    const result = await apiPost<MergeResult>('/api/v1/config/merge', {
      from_branch: mergeFrom.value,
      into_branch: props.current,
      author: 'ui',
    })
    if (result?.success) {
      ElMessage.success('合并成功')
    } else if (result?.conflict_files?.length) {
      ElMessage.warning(`冲突: ${result.conflict_files.join(', ')}`)
      // 加载第一个冲突文件内容
      conflictSection.value = result.conflict_files[0]
      await loadConflict(conflictSection.value)
    }
    emit('reload')
  } catch { /* 取消 */ }
}

async function loadConflict(section: string) {
  try {
    const data = await apiGet<{ content_with_markers: string }>(`/api/v1/config/conflict/${section}`)
    conflictContent.value = data?.content_with_markers || ''
  } catch { conflictContent.value = '(加载失败)' }
}

async function resolveConflict() {
  if (!conflictSection.value || !resolvedContent.value) return
  try {
    await apiPut(`/api/v1/config/conflict/${conflictSection.value}`, {
      resolved_content: resolvedContent.value,
      author: 'ui',
    })
    ElMessage.success('冲突已解决')
    conflictSection.value = ''
    conflictContent.value = ''
    resolvedContent.value = ''
    emit('reload')
  } catch { ElMessage.error('解决失败') }
}
</script>

<template>
<div>
  <!-- 分支列表 -->
  <el-table :data="branches" size="small" max-height="200">
    <el-table-column prop="name" label="分支" width="150">
      <template #default="{ row }">
        <span :style="{fontWeight: (row as GitBranch).is_current ? 'bold' : 'normal'}">
          {{ (row as GitBranch).name }}
        </span>
      </template>
    </el-table-column>
    <el-table-column prop="last_commit" label="最后提交" width="100" />
    <el-table-column label="操作" width="80">
      <template #default="{ row }">
        <el-button v-if="!(row as GitBranch).is_current" size="small" text
          @click="switchBranch((row as GitBranch).name)"
        >切换</el-button>
      </template>
    </el-table-column>
  </el-table>

  <!-- 创建分支 -->
  <div style="margin-top:16px;display:flex;gap:8px">
    <el-input v-model="newBranchName" placeholder="新分支名" size="small" style="flex:1" />
    <el-button size="small" @click="createBranch">创建</el-button>
  </div>

  <!-- 合并 -->
  <div style="margin-top:12px;display:flex;gap:8px">
    <el-select v-model="mergeFrom" placeholder="选择来源分支" size="small" style="flex:1">
      <el-option v-for="b in branches.filter(b => !b.is_current)" :key="b.name" :label="b.name" :value="b.name" />
    </el-select>
    <el-button size="small" @click="mergeBranch" :disabled="!mergeFrom">合并到 {{ props.current }}</el-button>
  </div>

  <!-- 冲突解决 -->
  <div v-if="conflictSection" style="margin-top:16px;padding:12px;background:rgba(239,68,68,.1);border-radius:6px">
    <div style="font-weight:600;margin-bottom:8px;color:#ef4444">
      冲突: {{ conflictSection }}
    </div>
    <pre style="font-family:var(--font-mono);font-size:11px;max-height:200px;overflow:auto;white-space:pre-wrap;color:var(--color-orbit-text-primary)">{{ conflictContent }}</pre>
    <el-input v-model="resolvedContent" type="textarea" :rows="4" placeholder="输入解决后的内容..." style="margin-top:8px" />
    <el-button size="small" type="primary" @click="resolveConflict" style="margin-top:8px">提交解决</el-button>
  </div>
</div>
</template>
