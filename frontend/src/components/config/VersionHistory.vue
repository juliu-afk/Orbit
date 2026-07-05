<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiGet, apiPost } from '@/services/api'
import { ElMessage, ElMessageBox } from 'element-plus'

interface GitCommit {
  hash: string; full_hash: string; message: string
  author: string; timestamp: string
}

const props = defineProps<{ section: string }>()

const commits = ref<GitCommit[]>([])
const selectedCommit = ref<string | null>(null)
const diffContent = ref('')
const loadingDiff = ref(false)

watch(() => props.section, async (sec) => {
  if (!sec) return
  await loadHistory(sec)
  diffContent.value = ''
  selectedCommit.value = null
})

async function loadHistory(sec: string) {
  try {
    const data = await apiGet<GitCommit[]>(`/api/v1/config/${sec}/history?limit=30`)
    commits.value = data || []
  } catch { commits.value = [] }
}

async function viewDiff(hash: string) {
  selectedCommit.value = hash
  loadingDiff.value = true
  try {
    const data = await apiGet<{ unified_diff: string }>(
      `/api/v1/config/${props.section}/diff?from=${hash}&to=HEAD`
    )
    diffContent.value = data?.unified_diff || '(无差异)'
  } catch { diffContent.value = '(加载失败)' }
  loadingDiff.value = false
}

async function rollback(hash: string) {
  try {
    await ElMessageBox.confirm(`回滚到 ${hash}？`, '确认回滚', { type: 'warning' })
    await apiPost(`/api/v1/config/${props.section}/rollback`, {
      commit_hash: hash, author: 'ui',
    })
    ElMessage.success('回滚成功')
    await loadHistory(props.section)
    diffContent.value = ''
  } catch { /* 取消 */ }
}
</script>

<template>
<div>
  <!-- 提交列表 -->
  <el-table :data="commits" size="small" max-height="400" highlight-current-row
    @row-click="(row: GitCommit) => viewDiff(row.hash)"
  >
    <el-table-column prop="hash" label="Hash" width="80" />
    <el-table-column prop="message" label="消息" />
    <el-table-column prop="author" label="作者" width="80" />
    <el-table-column prop="timestamp" label="时间" width="100">
      <template #default="{ row }">
        {{ (row as GitCommit).timestamp?.slice(0, 16) || '' }}
      </template>
    </el-table-column>
    <el-table-column label="操作" width="70">
      <template #default="{ row }">
        <el-button size="small" type="danger" text
          @click.stop="rollback((row as GitCommit).hash)"
        >回滚</el-button>
      </template>
    </el-table-column>
  </el-table>

  <!-- Diff 面板 -->
  <div v-if="diffContent" style="margin-top:12px;padding:8px;background:rgba(0,0,0,.3);border-radius:4px;max-height:300px;overflow:auto">
    <pre style="font-family:var(--font-mono);font-size:11px;margin:0;white-space:pre-wrap;color:var(--color-orbit-text-primary)">{{ diffContent }}</pre>
  </div>
  <div v-if="loadingDiff" style="text-align:center;padding:20px;color:var(--color-orbit-text-muted)">加载 diff...</div>
</div>
</template>
