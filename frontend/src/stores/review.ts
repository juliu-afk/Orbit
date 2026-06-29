import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiPost, apiGet } from '@/services/api'

export interface ReviewDecision { id: string; filePath: string; hunkIndex: number; decision: 'approved'|'rejected'|'comment'; comment: string|null; decidedBy: string }
export interface ReviewComment { id: string; filePath: string; lineStart: number; lineEnd: number; body: string; status: 'open'|'in_progress'|'resolved'; assignedTo: string|null; createdBy: string }

export const useReviewStore = defineStore('review', () => {
  const reviewId = ref<string|null>(null); const taskId = ref<string|null>(null); const status = ref('pending')
  const decisions = ref<ReviewDecision[]>([]); const comments = ref<ReviewComment[]>([]); const loading = ref(false)

  async function createReview(tid: string) { loading.value = true; try { const d = await apiPost<{review_id:string;task_id:string;status:string}>('/api/v1/review/sessions',{task_id:tid,created_by:'user'}); reviewId.value=d.review_id; taskId.value=d.task_id; status.value=d.status } finally { loading.value=false } }
  async function fetchReview(rid: string) { loading.value = true; try { const d = await apiGet<{review_id:string;task_id:string;status:string}>(`/api/v1/review/sessions/${rid}`); reviewId.value=d.review_id; taskId.value=d.task_id; status.value=d.status } finally { loading.value=false } }
  async function recordDecision(fp: string, hi: number, dec: string, commentText?: string) { if(!reviewId.value)return; await apiPost(`/api/v1/review/sessions/${reviewId.value}/decisions`,{file_path:fp,hunk_index:hi,decision:dec,decided_by:'user',comment:commentText||null}); decisions.value.push({id:'',filePath:fp,hunkIndex:hi,decision:dec as ReviewDecision['decision'],comment:commentText||null,decidedBy:'user'}) }
  async function addComment(fp: string, ls: number, le: number, body: string) { if(!reviewId.value)return; await apiPost(`/api/v1/review/sessions/${reviewId.value}/comments`,{file_path:fp,line_start:ls,line_end:le,body,created_by:'user'}); comments.value.push({id:'',filePath:fp,lineStart:ls,lineEnd:le,body,status:'open',assignedTo:null,createdBy:'user'}) }
  async function transitionStatus(ns: string) { if(!reviewId.value)return; await apiPost(`/api/v1/review/sessions/${reviewId.value}/status`,{status:ns}); status.value=ns }

  return { reviewId, taskId, status, decisions, comments, loading, createReview, fetchReview, recordDecision, addComment, transitionStatus }
})
