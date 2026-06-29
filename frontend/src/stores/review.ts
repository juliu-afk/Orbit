/** 审查状态管理——审查会话、决定、注释 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiPost, apiGet } from '@/services/api'

export interface ReviewDecision {
  id: string
  filePath: string
  hunkIndex: number
  decision: 'approved' | 'rejected' | 'comment'
  comment: string | null
  decidedBy: string
}

export interface ReviewComment {
  id: string
  filePath: string
  lineStart: number
  lineEnd: number
  body: string
  status: 'open' | 'in_progress' | 'resolved'
  assignedTo: string | null
  createdBy: string
}

export const useReviewStore = defineStore('review', () => {
  const reviewId = ref<string | null>(null)
  const taskId = ref<string | null>(null)
  const status = ref<string>('pending')
  const decisions = ref<ReviewDecision[]>([])
  const comments = ref<ReviewComment[]>([])
  const loading = ref(false)

  const summary = computed(() => {
    const byFile: Record<string, { approved: number; rejected: number; comment: number }> = {}
    for (const d of decisions.value) {
      if (!byFile[d.filePath]) byFile[d.filePath] = { approved: 0, rejected: 0, comment: 0 }
      byFile[d.filePath][d.decision]++
    }
    return { byFile, total: decisions.value.length }
  })

  async function createReview(tid: string) {
    loading.value = true
    try {
      const data = await apiPost<{ review_id: string; task_id: string; status: string }>(
        '/api/v1/review/sessions', { task_id: tid, created_by: 'user' }
      )
      reviewId.value = data.review_id
      taskId.value = data.task_id
      status.value = data.status
    } finally {
      loading.value = false
    }
  }

  async function fetchReview(rid: string) {
    loading.value = true
    try {
      const data = await apiGet<{ review_id: string; task_id: string; status: string }>(
        `/api/v1/review/sessions/${rid}`
      )
      reviewId.value = data.review_id
      taskId.value = data.task_id
      status.value = data.status
    } finally {
      loading.value = false
    }
  }

  async function recordDecision(filePath: string, hunkIndex: number, decision: string, commentText?: string) {
    if (!reviewId.value) return
    await apiPost(`/api/v1/review/sessions/${reviewId.value}/decisions`, {
      file_path: filePath,
      hunk_index: hunkIndex,
      decision,
      decided_by: 'user',
      comment: commentText || null,
    })
    decisions.value.push({
      id: '',
      filePath,
      hunkIndex,
      decision: decision as ReviewDecision['decision'],
      comment: commentText || null,
      decidedBy: 'user',
    })
  }

  async function addComment(filePath: string, lineStart: number, lineEnd: number, body: string) {
    if (!reviewId.value) return
    await apiPost(`/api/v1/review/sessions/${reviewId.value}/comments`, {
      file_path: filePath,
      line_start: lineStart,
      line_end: lineEnd,
      body,
      created_by: 'user',
    })
    comments.value.push({
      id: '',
      filePath,
      lineStart,
      lineEnd,
      body,
      status: 'open',
      assignedTo: null,
      createdBy: 'user',
    })
  }

  async function transitionStatus(newStatus: string) {
    if (!reviewId.value) return
    await apiPost(`/api/v1/review/sessions/${reviewId.value}/status`, { status: newStatus })
    status.value = newStatus
  }

  return {
    reviewId, taskId, status, decisions, comments, loading, summary,
    createReview, fetchReview, recordDecision, addComment, transitionStatus,
  }
})
