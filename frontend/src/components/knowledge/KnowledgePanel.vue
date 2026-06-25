<template>
  <div class="knowledge-panel">
    <el-card shadow="never" class="panel-card">
      <template #header>???</template>
      <div class="kb-search">
        <el-input
          v-model="domain"
          placeholder="?? (accounting)"
          size="small"
          style="width: 120px; margin-right: 8px"
        />
        <el-input
          v-model="concept"
          placeholder="???"
          size="small"
          style="width: 160px; margin-right: 8px"
          @keyup.enter="handleQuery"
        />
        <el-button size="small" @click="handleQuery" :loading="store.loading">Query</el-button>
        <el-button size="small" type="warning" @click="handleValidate">????</el-button>
      </div>

      <div v-if="store.currentConcept" class="kb-result">
        <div class="kb-concept-name">{{ store.currentConcept.concept }}</div>
        <div class="kb-definition">{{ store.currentConcept.definition }}</div>
        <div v-if="store.currentConcept.formula" class="kb-formula">
          ???{{ store.currentConcept.formula }}
        </div>
      </div>

      <div v-if="store.complianceResult" class="kb-compliance">
        <el-tag :type="complianceTagType" size="small">{{ store.complianceResult.status }}</el-tag>
        <div v-if="store.complianceResult.violations.length > 0" class="kb-violations">
          <div v-for="v in store.complianceResult.violations" :key="v" class="kb-violation">
            {{ v }}
          </div>
        </div>
      </div>

      <div v-if="store.error" class="kb-error">{{ store.error }}</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useKnowledgeStore } from '@/stores/knowledge'

const store = useKnowledgeStore()
const domain = ref('accounting')
const concept = ref('')

const complianceTagType = computed(() => {
  const s = store.complianceResult?.status || ''
  if (s === 'pass') return 'success'
  if (s === 'violation') return 'danger'
  return 'warning'
})

function handleQuery() {
  if (!domain.value || !concept.value) return
  store.queryConcept(domain.value, concept.value)
}

function handleValidate() {
  if (!domain.value || !concept.value) return
  store.validateCompliance(domain.value, concept.value)
}
</script>

<style scoped>
.knowledge-panel { margin-bottom: 12px; }
.panel-card { background: #12122a; border: 1px solid #2a2a4a; }
.kb-search { display: flex; align-items: center; margin-bottom: 12px; }
.kb-result { padding: 8px; background: #0a0a14; border-radius: 6px; margin-top: 8px; }
.kb-concept-name { font-size: 15px; color: #e0e0e0; font-weight: 600; margin-bottom: 4px; }
.kb-definition { font-size: 13px; color: #8888aa; line-height: 1.5; }
.kb-formula { font-size: 12px; color: #646cff; margin-top: 6px; font-family: monospace; }
.kb-compliance { margin-top: 8px; padding: 8px; background: #0a0a14; border-radius: 6px; }
.kb-violations { margin-top: 6px; }
.kb-violation { font-size: 12px; color: #ff9800; margin-bottom: 2px; }
.kb-error { margin-top: 8px; color: #f44336; font-size: 12px; }
</style>
