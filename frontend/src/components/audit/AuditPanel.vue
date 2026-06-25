<template>
  <div class="audit-panel">
    <el-card shadow="never" class="panel-card">
      <template #header>
        <el-button size="small" style="float: right" @click="store.fetchLessons()" :loading="store.loading">
        </el-button>
      </template>

      <div class="audit-search">
        <el-input
          v-model="taskId"
          placeholder="? task_id ?????"
          size="small"
          style="width: 200px; margin-right: 8px"
          @keyup.enter="handleFetchAudit"
        />
        <el-button size="small" @click="handleFetchAudit">??</el-button>
      </div>

      <div v-if="store.auditLogs.length > 0" class="audit-list">
        <div v-for="log in store.auditLogs" :key="log.lesson_id" class="audit-item">
          <div class="audit-item-header">
            <el-tag size="small" :type="log.outcome === 'success' ? 'success' : 'warning'">
              {{ log.outcome }}
            </el-tag>
            <span class="audit-domain">{{ log.domain }}</span>
          </div>
          <div class="audit-lesson">{{ log.lesson }}</div>
        </div>
      </div>

      <div v-if="store.lessons.length > 0" class="lesson-list">
        <div class="lesson-title">??? ({{ store.lessons.length }})</div>
        <div v-for="ls in store.lessons.slice(0, 10)" :key="ls.lesson_id" class="lesson-item">
          <span class="lesson-domain">{{ ls.domain }}</span>
          <span class="lesson-text">{{ ls.lesson }}</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAuditStore } from '@/stores/audit'

const store = useAuditStore()
const taskId = ref('')

function handleFetchAudit() {
  if (!taskId.value.trim()) return
  store.fetchAudit(taskId.value.trim())
}
</script>

<style scoped>
.audit-panel { margin-bottom: 12px; }
.panel-card { background: #12122a; border: 1px solid #2a2a4a; }
.audit-search { margin-bottom: 12px; display: flex; align-items: center; }
.audit-list { margin-top: 8px; }
.audit-item { padding: 8px; background: #0a0a14; border-radius: 6px; margin-bottom: 6px; }
.audit-item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.audit-domain { font-size: 12px; color: #646cff; }
.audit-lesson { font-size: 13px; color: #8888aa; }
.lesson-list { margin-top: 12px; }
.lesson-title { font-size: 13px; color: #8888aa; margin-bottom: 6px; }
.lesson-item { padding: 4px 8px; background: #0a0a14; border-radius: 4px; margin-bottom: 4px; display: flex; gap: 8px; }
.lesson-domain { font-size: 12px; color: #646cff; min-width: 80px; }
.lesson-text { font-size: 12px; color: #8888aa; }
</style>
