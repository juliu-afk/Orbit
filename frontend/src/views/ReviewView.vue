<!-- 审查主页面——Step 9 Phase 1 核心界面 -->
<template>
  <div class="review-view">
    <!-- 顶栏 -->
    <div class="review-toolbar">
      <el-button text @click="$router.push('/dashboard')">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <span class="task-info" v-if="review.taskId">
        Task: {{ review.taskId.slice(0, 8) }}...
      </span>
      <el-tag :type="statusTagType">{{ statusLabel }}</el-tag>
      <div class="toolbar-spacer" />
      <el-button
        v-if="review.status === 'approved'"
        type="primary"
        @click="showCommitDialog = true"
      >
        提交
      </el-button>
      <el-button
        v-if="review.status === 'in_review'"
        type="warning"
        @click="review.transitionStatus('changes_requested')"
      >
        打回重做
      </el-button>
      <el-button
        v-if="review.status === 'in_review'"
        type="success"
        @click="review.transitionStatus('approved')"
      >
        批准全部
      </el-button>
    </div>

    <!-- 主体 -->
    <div class="review-body">
      <!-- 左侧文件树 -->
      <FileTreePanel
        class="review-sidebar"
        :tree-data="fileTree"
        :selected-file="editor.currentFile"
        @select-file="onSelectFile"
      />

      <!-- 中央 Diff -->
      <div class="review-main">
        <div v-if="!editor.currentFile" class="no-file">
          <el-empty description="选择文件开始审查" :image-size="80" />
        </div>
        <MonacoDiffEditor
          v-else
          :key="editor.currentFile"
          :original="editor.original"
          :modified="editor.modified"
          :language="editor.language"
          height="100%"
        />
      </div>
    </div>

    <!-- 底部面板 -->
    <div class="review-bottom">
      <el-tabs>
        <el-tab-pane label="问题">
          <ProblemPanel :diagnostics="diagnosticsStore.diagnostics" />
        </el-tab-pane>
        <el-tab-pane :label="`审查决定 (${review.decisions.length})`">
          <div class="decision-list">
            <div
              v-for="(d, i) in review.decisions.slice(-20)"
              :key="d.id || `${d.filePath}:${d.hunkIndex}-${i}`"
              class="decision-item"
            >
              <el-tag size="small" :type="d.decision === 'approved' ? 'success' : 'danger'">
                {{ d.decision === 'approved' ? '已批' : '打回' }}
              </el-tag>
              <span class="decision-file">{{ d.filePath.split('/').pop() }}</span>
              <span class="decision-hunk">hunk #{{ d.hunkIndex }}</span>
              <span v-if="d.comment" class="decision-comment">{{ d.comment.slice(0, 40) }}</span>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- Commit 对话框 -->
    <el-dialog v-model="showCommitDialog" title="提交代码" width="500px">
      <el-input
        v-model="commitMessage"
        type="textarea"
        :rows="3"
        placeholder="commit message（Conventional Commits 格式）"
      />
      <div class="commit-options">
        <el-checkbox v-model="signCommit" @change="onSignToggle">GPG 签名</el-checkbox>
        <el-select
          v-if="signCommit && gitStore.gpgKeys.length"
          v-model="selectedGpgKey"
          placeholder="选择 GPG 密钥"
          size="small"
          style="width: 260px; margin-left: 12px"
        >
          <el-option
            v-for="k in gitStore.gpgKeys"
            :key="k.id"
            :label="`${k.name} <${k.email}>`"
            :value="k.id"
          />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="showCommitDialog = false">取消</el-button>
        <el-button type="primary" :loading="gitStore.committing" @click="doCommit">
          确认提交
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import MonacoDiffEditor from '@/components/editor/MonacoDiffEditor.vue'
import FileTreePanel from '@/components/editor/FileTreePanel.vue'
import ProblemPanel from '@/components/editor/ProblemPanel.vue'
import { useReviewStore } from '@/stores/review'
import { useEditorStore } from '@/stores/editor'
import { useDiagnosticsStore } from '@/stores/diagnostics'
import { useGitStore } from '@/stores/gitStore'
import { apiGet } from '@/services/api'
import type { FileNode } from '@/components/editor/FileTreePanel.vue'

const route = useRoute()
const review = useReviewStore()
const editor = useEditorStore()
const diagnosticsStore = useDiagnosticsStore()
const gitStore = useGitStore()

const showCommitDialog = ref(false)
const commitMessage = ref('')
const signCommit = ref(false)
const selectedGpgKey = ref('')

const fileTree = ref<FileNode[]>([])

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    pending: '待审查', in_review: '审查中',
    changes_requested: '已打回', approved: '已批准', merged: '已合并',
  }
  return map[review.status] ?? review.status
})

const statusTagType = computed(() => {
  const map: Record<string, string> = {
    pending: 'info', in_review: '', changes_requested: 'danger', approved: 'success', merged: 'info',
  }
  return map[review.status] ?? ''
})

function onSelectFile(path: string) {
  editor.openFile(path, 'HEAD', null)
}

function onSignToggle(val: boolean) {
  if (val as unknown as boolean && !gitStore.gpgKeys.length) {
    gitStore.fetchGpgKeys()
  }
}

onMounted(async () => {
  const taskId = route.params.taskId as string
  await review.createReview(taskId)
  gitStore.fetchGpgKeys()
  diagnosticsStore.fetchDiagnostics(taskId)

  try {
    const data = await apiGet<{ files: { path: string }[] }>('/api/v1/files/tree')
    fileTree.value = buildFileTree(data.files || [])
  } catch { /* 文件树加载失败不阻塞审查 */ }
})

function buildFileTree(files: { path: string }[]): FileNode[] {
  const root: FileNode[] = []
  const dirMap = new Map<string, FileNode>()
  for (const f of files) {
    const parts = f.path.split('/')
    let parent = root
    let currentPath = ''
    for (let i = 0; i < parts.length; i++) {
      const name = parts[i]
      const isLast = i === parts.length - 1
      currentPath = currentPath ? `${currentPath}/${name}` : name
      if (isLast) {
        parent.push({ name, path: f.path, isDir: false })
      } else {
        if (!dirMap.has(currentPath)) {
          const dir: FileNode = { name, path: currentPath, isDir: true, children: [] }
          dirMap.set(currentPath, dir)
          parent.push(dir)
        }
        parent = dirMap.get(currentPath)!.children!
      }
    }
  }
  function sort(nodes: FileNode[]) {
    nodes.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    for (const n of nodes) if (n.children) sort(n.children)
  }
  sort(root)
  return root
}

async function doCommit() {
  if (!commitMessage.value.trim()) {
    ElMessage.warning('请输入 commit message')
    return
  }
  const result = await gitStore.commit(
    commitMessage.value,
    [],
    signCommit.value,
    selectedGpgKey.value || undefined,
  )
  if (result) {
    ElMessage.success(
      `提交成功: ${result.commit_hash.slice(0, 8)}${result.verified ? ' ✅ Verified' : ''}`
    )
    showCommitDialog.value = false
    await review.transitionStatus('merged')
  }
}
</script>

<style scoped>
.review-view { height: 100vh; display: flex; flex-direction: column; background: var(--el-bg-color-page); }
.review-toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 6px 16px; background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
}
.task-info { font-size: 13px; color: var(--el-text-color-secondary); }
.toolbar-spacer { flex: 1; }
.review-body { flex: 1; display: flex; overflow: hidden; }
.review-sidebar { width: 240px; flex-shrink: 0; border-right: 1px solid var(--el-border-color-light); overflow: hidden; }
.review-main { flex: 1; overflow: hidden; }
.no-file { display: flex; align-items: center; justify-content: center; height: 100%; }
.review-bottom { height: 200px; border-top: 1px solid var(--el-border-color-light); background: var(--el-bg-color); overflow: hidden; }
.review-bottom :deep(.el-tabs__content) { height: calc(100% - 40px); overflow-y: auto; }
.decision-list { padding: 4px 12px; }
.decision-item { display: flex; align-items: center; gap: 8px; padding: 2px 0; font-size: 13px; }
.decision-file { color: var(--el-text-color-primary); }
.decision-hunk { color: var(--el-text-color-secondary); font-size: 12px; }
.decision-comment { color: var(--el-text-color-placeholder); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px; }
.commit-options { margin-top: 12px; display: flex; align-items: center; }
</style>
