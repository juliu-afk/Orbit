<!-- 审查主页面——Step 9 Phase 1 核心界面 -->
<template>
  <div class="review-view">
    <div class="review-toolbar">
      <el-button text @click="$router.push('/dashboard')"><el-icon><ArrowLeft /></el-icon>Back</el-button>
      <span class="task-info" v-if="review.taskId">Task: {{ review.taskId.slice(0, 8) }}...</span>
      <el-tag :type="statusTagType">{{ statusLabel }}</el-tag>
      <el-button text size="small" @click="focusTab('search')"><el-icon><Search /></el-icon></el-button>
      <el-button text size="small" @click="focusTab('outline')"><el-icon><List /></el-icon></el-button>
      <div class="toolbar-spacer" />
      <el-button v-if="review.status === 'approved'" type="primary" @click="showCommitDialog = true">Commit</el-button>
      <el-button v-if="review.status === 'in_review'" type="warning" @click="review.transitionStatus('changes_requested')">Reject All</el-button>
      <el-button v-if="review.status === 'in_review'" type="success" @click="review.transitionStatus('approved')">Approve All</el-button>
    </div>
    <div class="review-body">
      <div class="review-sidebar">
        <FileTreePanel :tree-data="fileTree" :selected-file="editor.currentFile" @select-file="onSelectFile" />
        <ReviewCommentPanel v-if="review.taskId && editor.currentFile" :review-id="review.taskId" :file="editor.currentFile" :line="editor.currentLine" />
      </div>
      <div class="review-main">
        <div v-if="!editor.currentFile" class="no-file"><el-empty description="Select a file to review" :image-size="80" /></div>
        <MonacoDiffEditor v-else :key="editor.currentFile" :original="editor.original" :modified="editor.modified" :language="editor.language" height="100%" />
      </div>
    </div>
    <div class="review-bottom">
      <el-tabs v-model="activeBottomTab">
        <el-tab-pane label="Problems" name="problems"><ProblemPanel :diagnostics="diag.diagnostics" /></el-tab-pane>
        <el-tab-pane :label="`Decisions (${review.decisions.length})`" name="decisions">
          <div class="decision-list">
            <div v-for="(d, i) in review.decisions.slice(-20)" :key="i" class="decision-item">
              <el-tag size="small" :type="d.decision === 'approved' ? 'success' : 'danger'">{{ d.decision }}</el-tag>
              <span class="decision-file">{{ d.filePath.split('/').pop() }}</span>
              <span class="decision-hunk">hunk #{{ d.hunkIndex }}</span>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="Outline" name="outline"><OutlinePanel :items="outlineItems" @select="onOutlineNavigate" /></el-tab-pane>
        <el-tab-pane label="Search" name="search"><SearchPanel /></el-tab-pane>
        <el-tab-pane label="Tests" name="tests"><TestPanel /></el-tab-pane>
        <el-tab-pane label="Terminal" name="terminal"><TerminalPanel /></el-tab-pane>
      </el-tabs>
    </div>
    <el-dialog v-model="showCommitDialog" title="Commit" width="500px">
      <el-input v-model="commitMessage" type="textarea" :rows="3" placeholder="commit message (Conventional Commits)" />
      <div class="commit-options">
        <el-checkbox v-model="signCommit">GPG Sign</el-checkbox>
        <el-select v-if="signCommit && git.gpgKeys.length" v-model="selectedGpgKey" placeholder="Select GPG key" size="small" style="width:260px;margin-left:12px">
          <el-option v-for="k in git.gpgKeys" :key="k.id" :label="`${k.name} <${k.email}>`" :value="k.id" />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="showCommitDialog = false">Cancel</el-button>
        <el-button type="primary" :loading="git.committing" @click="doCommit">Commit</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Search, List } from '@element-plus/icons-vue'
import MonacoDiffEditor from '@/components/editor/MonacoDiffEditor.vue'
import FileTreePanel from '@/components/editor/FileTreePanel.vue'
import ProblemPanel from '@/components/editor/ProblemPanel.vue'
import OutlinePanel from '@/components/editor/OutlinePanel.vue'
import SearchPanel from '@/components/editor/SearchPanel.vue'
import TestPanel from '@/components/editor/TestPanel.vue'
import TerminalPanel from '@/components/editor/TerminalPanel.vue'
import ReviewCommentPanel from '@/components/editor/ReviewCommentPanel.vue'
import { useReviewStore } from '@/stores/review'
import { useEditorStore } from '@/stores/editor'
import { useDiagnosticsStore } from '@/stores/diagnostics'
import { useGitStore } from '@/stores/gitStore'
import { apiGet } from '@/services/api'
import type { FileNode } from '@/components/editor/FileTreePanel.vue'
import type { OutlineItem } from '@/components/editor/OutlinePanel.vue'

const route = useRoute()
const review = useReviewStore()
const editor = useEditorStore()
const diag = useDiagnosticsStore()
const git = useGitStore()

const showCommitDialog = ref(false); const commitMessage = ref(''); const signCommit = ref(false); const selectedGpgKey = ref('')
const fileTree = ref<FileNode[]>([])
const outlineItems = ref<OutlineItem[]>([])
const wsDir = ref('')
const activeBottomTab = ref('problems')

// 工具栏按钮→切换底部标签页
function focusTab(name: string) { activeBottomTab.value = name }

// 大纲条目点击——由 MonacoDiffEditor 内部实现跳转
function onOutlineNavigate(line: number) { activeBottomTab.value = 'problems' }  // P1-3: 切回diff视图

const statusLabel = computed(() => ({ pending:'Pending', in_review:'In Review', changes_requested:'Rejected', approved:'Approved', merged:'Merged' }[review.status] ?? review.status))
const statusTagType = computed(() => ({ pending:'info', in_review:'', changes_requested:'danger', approved:'success', merged:'info' }[review.status] ?? ''))

function onSelectFile(path: string) { editor.openFile(path, 'HEAD', null) }

onMounted(async () => {
  const tid = route.params.taskId as string
  await review.createReview(tid); git.fetchGpgKeys(); diag.fetchDiagnostics(tid)
  try {
    const data = await apiGet<{ files: { path: string }[] }>('/api/v1/files/tree')
    fileTree.value = buildTree(data.files || [])
  } catch {}
  // 加载大纲和工作区路径
  try { outlineItems.value = await apiGet<OutlineItem[]>('/api/v1/review/outline?task_id=' + tid) } catch {}
  try { const ws = await apiGet<{ path: string }>('/api/v1/workspace'); wsDir.value = ws.path } catch {}
})

function buildTree(files: { path: string }[]): FileNode[] {
  const root: FileNode[] = []; const dirMap = new Map<string, FileNode>()
  for (const f of files) {
    const parts = f.path.split('/'); let parent = root; let cur = ''
    for (let i = 0; i < parts.length; i++) {
      cur = cur ? `${cur}/${parts[i]}` : parts[i]
      if (i === parts.length - 1) parent.push({ name: parts[i], path: f.path, isDir: false })
      else { if (!dirMap.has(cur)) { const d: FileNode = { name: parts[i], path: cur, isDir: true, children: [] }; dirMap.set(cur, d); parent.push(d) } parent = dirMap.get(cur)!.children! }
    }
  }
  const sort = (n: FileNode[]) => { n.sort((a, b) => a.isDir !== b.isDir ? (a.isDir ? -1 : 1) : a.name.localeCompare(b.name)); n.filter(x => x.children).forEach(x => sort(x.children!)) }
  sort(root); return root
}

async function doCommit() {
  if (!commitMessage.value.trim()) { ElMessage.warning('Enter commit message'); return }
  const r = await git.commit(commitMessage.value, [], signCommit.value, selectedGpgKey.value || undefined)
  if (r) { ElMessage.success(`Committed: ${r.commit_hash.slice(0, 8)}${r.verified ? ' Verified' : ''}`); showCommitDialog.value = false; await review.transitionStatus('merged') }
}
</script>

<style scoped>
.review-view { height: 100vh; display: flex; flex-direction: column; background: var(--el-bg-color-page); }
.review-toolbar { display: flex; align-items: center; gap: 12px; padding: 6px 16px; background: var(--el-bg-color); border-bottom: 1px solid var(--el-border-color-light); }
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
.commit-options { margin-top: 12px; display: flex; align-items: center; }
</style>
