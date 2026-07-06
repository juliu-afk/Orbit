<!-- 审查注释面板——行级评论线程 (Phase 2.1) -->
<template>
  <div class="comment-panel">
    <div class="comment-header">Comments ({{ comments.length }})</div>
    <div v-if="comments.length" class="comment-list">
      <div v-for="c in comments" :key="c.id" class="comment-item" :class="'status-' + c.status">
        <div class="comment-meta">
          <span class="comment-file">{{ c.file.split('/').pop() }}:{{ c.line }}</span>
          <el-tag size="small">{{ c.status }}</el-tag>
          <span class="comment-author">{{ c.author }}</span>
        </div>
        <div class="comment-body">{{ c.body }}</div>
        <div v-if="c.reply" class="comment-reply">{{ c.reply }}</div>
      </div>
    </div>
    <div class="comment-input">
      <el-input v-model="newComment" placeholder="Add comment..." size="small" @keyup.enter="addComment" />
      <el-button size="small" @click="addComment">Post</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiPost, apiGet } from '@/services/api'

interface ThreadComment { id: string; file: string; line: number; body: string; status: string; author: string; reply?: string }
const props = defineProps<{ reviewId: string; file: string; line: number }>()
const comments = ref<ThreadComment[]>([])
const newComment = ref('')

async function loadComments() {
  try { const d = await apiGet<ThreadComment[]>(`/api/v1/review/sessions/${props.reviewId}/comments?file=${props.file}`); comments.value = d } catch (e) { if (import.meta.env.DEV) console.error('loadComments failed:', e) }
}
onMounted(() => loadComments())
async function addComment() {
  if (!newComment.value.trim()) return
  try {
    await apiPost(`/api/v1/review/sessions/${props.reviewId}/comments`, { file_path: props.file, line_start: props.line, line_end: props.line, body: newComment.value, created_by: 'user' })
    comments.value.push({ id: '', file: props.file, line: props.line, body: newComment.value, status: 'open', author: 'user' })
    newComment.value = ''
  } catch (e) { if (import.meta.env.DEV) console.error('addComment failed:', e) }
}
</script>

<style scoped>
.comment-panel { padding: 8px; }
.comment-header { font-weight: 600; font-size: 13px; margin-bottom: 8px; }
.comment-list { max-height: 250px; overflow-y: auto; }
.comment-item { padding: 4px 8px; margin-bottom: 4px; border-radius: 4px; border-left: 3px solid var(--el-color-primary); }
.comment-meta { display: flex; gap: 8px; align-items: center; font-size: 12px; }
.comment-file { color: var(--el-color-primary); }
.comment-author { color: var(--el-text-color-secondary); }
.comment-body { margin-top: 4px; font-size: 13px; }
.comment-reply { margin-top: 4px; padding: 4px 8px; background: var(--el-fill-color-light); border-radius: 3px; font-size: 12px; }
.comment-input { display: flex; gap: 8px; margin-top: 8px; }
</style>
