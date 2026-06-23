<!-- 候选项目卡片：项目名 + 匹配分数 + 原因 + 确认按钮 -->
<template>
  <div class="candidate-card" :class="{ 'candidate-card--top': isTop }">
    <div class="candidate-card__header">
      <span class="candidate-card__name">{{ candidate.project }}</span>
      <el-tag :type="scoreTagType" size="small">{{ scorePct }}%</el-tag>
    </div>
    <div class="candidate-card__body">
      <span class="candidate-card__reason">{{ reasonLabel }}</span>
      <span v-if="candidate.matched_keywords.length" class="candidate-card__keywords">
        匹配: {{ candidate.matched_keywords.join(', ') }}
      </span>
    </div>
    <div class="candidate-card__actions">
      <el-button size="small" type="primary" @click="$emit('confirm', candidate.project)">
        确认
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Candidate } from '@/stores/chat'

const props = defineProps<{
  candidate: Candidate
  isTop?: boolean
}>()

defineEmits<{ confirm: [project: string] }>()

const scorePct = computed(() => Math.round(props.candidate.score * 100))
const scoreTagType = computed(() => {
  if (props.candidate.score >= 0.8) return 'success'
  if (props.candidate.score >= 0.5) return 'warning'
  return 'info'
})

const reasonLabel = computed(() => {
  const map: Record<string, string> = {
    name_exact: '名称精确匹配',
    tag_match: '标签匹配',
    desc_match: '描述匹配',
    session_history: '会话历史',
    fallback: '最近活跃',
  }
  return map[props.candidate.reason] || props.candidate.reason
})
</script>

<style scoped>
.candidate-card {
  background: #16163a;
  border: 1px solid #2a2a5a;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
  transition: border-color 0.2s;
}
.candidate-card--top { border-color: #4caf50; }
.candidate-card__header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.candidate-card__name {
  font-size: 16px; font-weight: 600; color: #e0e0e0;
}
.candidate-card__body {
  display: flex; flex-direction: column; gap: 4px;
  margin-bottom: 8px;
}
.candidate-card__reason { font-size: 12px; color: #8888aa; }
.candidate-card__keywords { font-size: 11px; color: #6666aa; }
.candidate-card__actions { display: flex; justify-content: flex-end; }
</style>
