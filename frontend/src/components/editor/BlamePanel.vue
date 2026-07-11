<!-- Git Blame 面板（PR5）——逐行作者标注，区分 Agent 与 Human -->
<script setup lang="ts">
import { useBlameStore } from '@/stores/blame'

const store = useBlameStore()

// author-time 是 Unix 秒时间戳字符串，转本地日期
function fmtTime(t: string): string {
  const sec = Number(t)
  if (!sec) return '—'
  // 只显示年月日，逐行不需要精确到秒
  return new Date(sec * 1000).toISOString().slice(0, 10)
}

// author 可能是 'Name <email>' 格式，只取名字
function authorName(a: string): string {
  return a.includes('<') ? a.split('<')[0].trim() : a
}
</script>

<template>
<div class="blame-panel">
  <div v-if="store.loading" class="blame-empty">加载 blame…</div>
  <div v-else-if="!store.lines.length" class="blame-empty">打开文件查看 git blame（需 git 仓库）</div>
  <table v-else class="blame-table">
    <tbody>
      <tr v-for="(l, i) in store.lines" :key="i">
        <td class="lineno">{{ i + 1 }}</td>
        <td class="author" :class="{ agent: l.is_agent }" :title="l.author">
          <span v-if="l.is_agent" class="agent-badge">AI</span>{{ authorName(l.author) }}
        </td>
        <td class="time">{{ fmtTime(l.time) }}</td>
        <td class="content mono">{{ l.content }}</td>
      </tr>
    </tbody>
  </table>
</div>
</template>

<style scoped>
.blame-panel { height: 100%; overflow: auto; font-size: 12px; }
.blame-empty { padding: 16px; text-align: center; color: var(--el-text-color-secondary); }
.blame-table { width: 100%; border-collapse: collapse; }
.blame-table td { padding: 1px 8px; white-space: nowrap; border-bottom: 1px solid var(--el-border-color-lighter); }
.lineno { color: var(--el-text-color-placeholder); text-align: right; width: 40px; user-select: none; }
.author { max-width: 120px; overflow: hidden; text-overflow: ellipsis; color: var(--el-text-color-secondary); }
.author.agent { color: var(--el-color-warning); }
.agent-badge { display: inline-block; background: var(--el-color-warning); color: #000; font-size: 9px; padding: 0 3px; border-radius: 2px; margin-right: 4px; }
.time { color: var(--el-text-color-placeholder); font-size: 11px; }
.content { font-family: var(--font-mono); overflow: hidden; text-overflow: ellipsis; max-width: 400px; }
.mono { font-family: var(--font-mono); }
</style>
