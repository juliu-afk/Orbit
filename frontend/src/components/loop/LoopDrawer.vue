<!-- 定时任务抽屉（PR4）——Cron-like 循环任务管理：列表 + 新建 + 暂停/恢复/停止 -->
<script setup lang="ts">
import { watch, ref } from 'vue'
import { useLoopStore } from '@/stores/loop'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const store = useLoopStore()
const newInterval = ref('')
const newCommand = ref('')
const createError = ref('')

// 打开抽屉时刷新列表
watch(() => props.show, (visible) => {
  if (visible) store.fetchLoops()
})

async function submit() {
  createError.value = ''
  const interval = newInterval.value.trim()
  const command = newCommand.value.trim()
  if (!interval || !command) { createError.value = '间隔和命令都必填'; return }
  try {
    await store.createLoop(interval, command)
    newInterval.value = ''
    newCommand.value = ''
  } catch {
    createError.value = '创建失败——间隔格式：30s/5m/1h/hourly/daily 或 cron 5 字段'
  }
}

function fmtInterval(sec: number): string {
  if (sec % 3600 === 0) return `${sec / 3600}h`
  if (sec % 60 === 0) return `${sec / 60}m`
  return `${sec}s`
}
</script>

<template>
<el-drawer :model-value="props.show" title="定时任务" direction="rtl" size="520px" @update:model-value="emit('update:show', $event as boolean)">
  <div class="loop-panel">
    <!-- 新建表单 -->
    <div class="loop-create">
      <el-input v-model="newInterval" size="small" placeholder="间隔 如 5m / hourly / 0 9 * * *" style="width:200px" />
      <el-input v-model="newCommand" size="small" placeholder="shell 命令" @keyup.enter="submit" />
      <el-button size="small" type="primary" @click="submit">新建</el-button>
    </div>
    <div v-if="createError" class="loop-err">{{ createError }}</div>

    <!-- 列表 -->
    <div v-if="store.loading" class="loop-empty">加载中…</div>
    <div v-else-if="!store.loops.length" class="loop-empty">暂无定时任务</div>
    <table v-else class="loop-table">
      <thead>
        <tr><th>命令</th><th>间隔</th><th>状态</th><th>已运行</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="l in store.loops" :key="l.id">
          <td class="mono cmd" :title="l.command">{{ l.command }}</td>
          <td class="mono">{{ fmtInterval(l.interval_seconds) }}</td>
          <td><span class="status" :class="'st-' + l.status">{{ l.status }}</span></td>
          <td>{{ l.run_count }}</td>
          <td class="actions">
            <el-button v-if="l.status !== 'paused'" size="small" text @click="store.pauseLoop(l.id)">暂停</el-button>
            <el-button v-else size="small" text type="success" @click="store.resumeLoop(l.id)">恢复</el-button>
            <el-button size="small" text type="danger" @click="store.stopLoop(l.id)">停止</el-button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</el-drawer>
</template>

<style scoped>
.loop-panel { font-family: var(--font-mono); font-size: 12px; }
.loop-create { display: flex; gap: 8px; margin-bottom: 8px; }
.loop-err { color: var(--el-color-danger); font-size: 11px; margin-bottom: 8px; }
.loop-empty { padding: 24px; text-align: center; color: var(--color-orbit-text-muted); }
.loop-table { width: 100%; border-collapse: collapse; }
.loop-table th, .loop-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--color-orbit-border); }
.loop-table th { color: var(--color-orbit-text-secondary); font-weight: 500; font-size: 11px; }
.mono { font-family: var(--font-mono); }
.cmd { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status { padding: 1px 8px; border-radius: 3px; font-size: 10px; }
.st-active { background: rgba(76,175,80,.15); color: #67c23a; }
.st-paused { background: rgba(230,162,60,.15); color: #e6a23c; }
.st-stopped { background: rgba(144,147,153,.15); color: #909399; }
.actions { white-space: nowrap; }
</style>
