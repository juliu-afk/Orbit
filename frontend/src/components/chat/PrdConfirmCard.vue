<!-- PRD 验收确认面板——从 ChatPanel.vue 拆分 -->
<template>
  <div v-if="showAcceptanceOptions" class="acceptance-panel">
    <div class="acceptance-title">选择验收标准</div>
    <label v-for="opt in acceptanceOptions" :key="opt" class="acceptance-option">
      <input type="checkbox" :value="opt" v-model="selectedAcceptance" />
      <span>{{ opt }}</span>
    </label>
    <label class="acceptance-option">
      <input type="checkbox" v-model="useCustomAcceptance" />
      <span>自定义</span>
    </label>
    <input
      v-if="useCustomAcceptance"
      v-model="customAcceptance"
      class="acceptance-input"
      placeholder="请输入自定义验收标准..."
    />
    <el-button type="primary" size="small" @click="submitAcceptance">提交</el-button>
  </div>

  <div v-if="showPrdConfirm" class="prd-panel">
    <div class="prd-title">请确认需求文档</div>
    <div class="prd-field">
      <label>目标</label>
      <textarea v-model="editablePrd.goal" rows="2" class="prd-input"></textarea>
    </div>
    <div class="prd-field">
      <label>范围</label>
      <textarea v-model="editablePrd.scope" rows="2" class="prd-input"></textarea>
    </div>
    <div class="prd-field">
      <label>验收标准</label>
      <div v-for="(_ac, i) in editablePrd.acceptance_criteria" :key="i" class="prd-ac-item">
        <input v-model="editablePrd.acceptance_criteria[i]" class="prd-input" />
      </div>
    </div>
    <div class="prd-actions">
      <el-button type="primary" @click="handleConfirmPrd">确认并提交任务</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { StructuredPRD } from '@/stores/chat'

defineProps<{
  showAcceptanceOptions: boolean
  showPrdConfirm: boolean
  acceptanceOptions: string[]
  editablePrd: StructuredPRD
}>()

const emit = defineEmits<{
  (e: 'submit-acceptance', criteria: string[]): void
  (e: 'confirm-prd'): void
}>()

const selectedAcceptance = ref<string[]>([])
const useCustomAcceptance = ref(false)
const customAcceptance = ref('')

function submitAcceptance() {
  const merged = [...selectedAcceptance.value]
  if (useCustomAcceptance.value && customAcceptance.value.trim()) {
    merged.push(customAcceptance.value.trim())
  }
  emit('submit-acceptance', merged)
  selectedAcceptance.value = []
  useCustomAcceptance.value = false
  customAcceptance.value = ''
}

function handleConfirmPrd() {
  emit('confirm-prd')
}
</script>
