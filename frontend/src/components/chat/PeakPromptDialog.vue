<script setup lang="ts">
import { ref } from 'vue'

export interface PeakPromptData {
  goal_id: string; provider: string; next_offpeak: string; prompt: string
}

const visible = defineModel<boolean>('visible', { required: true })
const props = defineProps<{ data: PeakPromptData | null }>()
const emit = defineEmits<{ defer: [goalId: string]; urgent: [goalId: string]; cancel: [] }>()
const submitting = ref(false)


</script>

<template>
  <el-dialog v-model="visible" title="高峰期避让" width="420px" :close-on-click-modal="false">
    <div style="display:flex;flex-direction:column;gap:12px">
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>当前为 <strong>{{ data?.provider }}</strong> 高峰期</template>
        API 响应可能较慢，Token 成本较高。
      </el-alert>
      <p v-if="data?.next_offpeak" style="margin:0;font-size:13px;color:#888">
        下一个低峰窗口：{{ formatTime(data.next_offpeak) }}
      </p>
    </div>
    <template #footer>
      <el-button @click="emit('cancel'); visible = false" :disabled="submitting">取消</el-button>
      <el-button type="primary" @click="emit('defer', props.data?.goal_id ?? ''); submitting = true" :loading="submitting">延迟到低峰执行</el-button>
      <el-button type="warning" @click="emit('urgent', props.data?.goal_id ?? ''); submitting = true" :disabled="submitting">立即执行（紧急）</el-button>
    </template>
  </el-dialog>
</template>
