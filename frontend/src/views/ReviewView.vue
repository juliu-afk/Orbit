<!-- 代码审查视图（PR7）——审查会话：文件树 + diff + 风险评分 + 行评论 + 决策 + 签名提交 -->
<script setup lang="ts">
import { ref, computed, onMounted, defineAsyncComponent, unref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useReviewStore } from '@/stores/review'
import { useEditorStore } from '@/stores/editor'
import { useGitStore } from '@/stores/gitStore'
import FileTreePanel from '@/components/editor/FileTreePanel.vue'
import type { FileNode } from '@/components/editor/FileTreePanel.vue'
import RiskPanel from '@/components/insights/RiskPanel.vue'
import ReviewCommentPanel from '@/components/editor/ReviewCommentPanel.vue'
import { apiGet } from '@/services/api'

// WHY 懒加载 Monaco：4MB chunk 只在打开文件时加载；同时避免测试环境 jsdom 缺 queryCommandSupported
const MonacoDiffEditor = defineAsyncComponent(() => import('@/components/editor/MonacoDiffEditor.vue'))

const route = useRoute()
const taskId = String(route.params.taskId || '')

const review = useReviewStore()
const editor = useEditorStore()
const git = useGitStore()

const fileTree = ref<FileNode[]>([])
const selectedLine = ref(1)
const risks = ref<Array<{ file: string; score: number; level: string; factors: string[] }>>([])

// status 展示映射——spec 期望 'In Review' / 'Approved'。
// WHY unref：真实 pinia store 自动解包，但测试 mock 传裸 ref，需显式 unref 兼容两者。
const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending', in_review: 'In Review', approved: 'Approved', rejected: 'Rejected', merged: 'Merged',
}
const rawStatus = computed(() => String(unref(review.status)))
const statusLabel = computed(() => STATUS_LABELS[rawStatus.value] || rawStatus.value)
const isInReview = computed(() => rawStatus.value === 'in_review')
const isApproved = computed(() => rawStatus.value === 'approved')
// WHY unref：兼容测试 mock 的裸 ref 与真实 store 的自动解包
const currentFile = computed(() => unref(editor.currentFile) as string | null)

function goBack() {
  window.history.back()
}

onMounted(async () => {
  // 建立/恢复审查会话
  await review.createReview(taskId)
  await review.transitionStatus('in_review')
  await git.fetchGpgKeys()
  fetchRisks()
  fetchFileTree()
})

// 风险评分——/insights/risk 返回裸数组(非 {code,data})，用原生 fetch
async function fetchRisks() {
  if (!review.reviewId) return
  try {
    const r = await fetch(`/api/v1/insights/risk?task_id=${encodeURIComponent(review.reviewId)}`)
    risks.value = r.ok ? await r.json() : []
  } catch {
    risks.value = []
  }
}

async function fetchFileTree() {
  try {
    const d = await apiGet<{ files: Array<{ path: string }> }>('/api/v1/files/tree')
    if (d.files) fileTree.value = buildTree(d.files)
  } catch { /* ignore */ }
}

function buildTree(files: Array<{ path: string }>): FileNode[] {
  const root: FileNode[] = []; const dirMap = new Map<string, FileNode>()
  for (const f of files) {
    const parts = f.path.split('/').filter(Boolean); let parent = root; let cp = ''
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i]; cp = cp ? `${cp}/${p}` : p
      if (i === parts.length - 1) parent.push({ name: p, path: f.path, isDir: false })
      else { let d = dirMap.get(cp); if (!d) { d = { name: p, path: cp, isDir: true, children: [] }; dirMap.set(cp, d); parent.push(d) } parent = d.children! }
    }
  }
  return root
}

async function onSelectFile(path: string) {
  await editor.openFile(path)
}

async function approveAll() {
  await review.transitionStatus('approved')
  ElMessage.success('已批准')
}
async function rejectAll() {
  await review.transitionStatus('rejected')
  ElMessage.warning('已拒绝')
}

async function doCommit() {
  const files = editor.currentFile ? [editor.currentFile] : []
  const keyId = git.gpgKeys[0]?.id
  try {
    await git.commit(`review: ${taskId}`, files, !!keyId, keyId)
    ElMessage.success('已提交')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '提交失败')
  }
}
</script>

<template>
<div class="review-view">
  <!-- 工具栏 -->
  <div class="review-toolbar">
    <el-button size="small" text @click="goBack">← Back</el-button>
    <span class="review-task">Task: {{ taskId }}</span>
    <el-tag :type="isApproved ? 'success' : 'warning'" size="small">{{ statusLabel }}</el-tag>
    <div class="toolbar-actions">
      <template v-if="isInReview">
        <el-button size="small" type="success" @click="approveAll">Approve All</el-button>
        <el-button size="small" type="danger" @click="rejectAll">Reject All</el-button>
      </template>
      <el-button v-if="isApproved" size="small" type="primary" :loading="git.committing" @click="doCommit">Commit</el-button>
    </div>
  </div>

  <div class="review-body">
    <!-- 侧栏：文件树 + 风险评分 -->
    <div class="review-sidebar">
      <FileTreePanel :tree-data="fileTree" :selected-file="editor.currentFile" :current-project-path="''" @select-file="onSelectFile" />
      <RiskPanel :risks="risks" />
    </div>

    <!-- 主区：diff + 行评论 -->
    <div class="review-main">
      <div v-if="!currentFile" class="no-file">Select a file to review</div>
      <template v-else>
        <MonacoDiffEditor :original="editor.original" :modified="editor.modified" :language="editor.language" height="60%" />
        <ReviewCommentPanel v-if="review.reviewId" :review-id="review.reviewId" :file="currentFile" :line="selectedLine" />
      </template>
    </div>
  </div>
</div>
</template>

<style scoped>
.review-view { display: flex; flex-direction: column; height: 100vh; background: var(--color-orbit-bg); color: var(--color-orbit-text); }
.review-toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 16px; border-bottom: 1px solid var(--color-orbit-border); font-family: var(--font-mono); font-size: 13px; }
.review-task { font-weight: 600; }
.toolbar-actions { margin-left: auto; display: flex; gap: 8px; }
.review-body { flex: 1; display: grid; grid-template-columns: 280px 1fr; min-height: 0; }
.review-sidebar { border-right: 1px solid var(--color-orbit-border); overflow-y: auto; display: flex; flex-direction: column; }
.review-main { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.no-file { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--color-orbit-text-muted); font-size: 14px; }
</style>
