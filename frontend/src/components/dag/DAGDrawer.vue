<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DagCanvas from '@/components/dag/DagCanvas.vue'
import { useTaskStore } from '@/stores/task'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', val: boolean): void }>()

const task = useTaskStore()
// 运行中（非终态）才可取消
const TERMINAL = ['IDLE', 'DONE', 'FAILED', 'CANCELLED']
const canCancel = computed(() => !!task.currentTaskId && !TERMINAL.includes(task.taskState))

async function onCancel() {
  try {
    await ElMessageBox.confirm('取消当前任务？将停止调度并标记为 CANCELLED。', '取消任务', {
      confirmButtonText: '取消任务', cancelButtonText: '返回', type: 'warning',
    })
  } catch { return }
  try {
    await task.cancelCurrentTask()
    ElMessage.success('任务已取消')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '取消失败')
  }
}
</script>
<template>
<el-drawer :model-value="props.show" title="DAG" direction="rtl" size="600px" @update:model-value="emit('update:show', $event as boolean)">
  <template #header>
    <div style="display:flex;align-items:center;gap:12px;width:100%">
      <span>DAG</span>
      <el-tag size="small">{{ task.taskState }}</el-tag>
      <el-button v-if="canCancel" size="small" type="danger" style="margin-left:auto" @click="onCancel">取消任务</el-button>
    </div>
  </template>
  <DagCanvas />
</el-drawer>
</template>
