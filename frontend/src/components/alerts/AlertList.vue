<!-- 告警列表：Element Plus 表格，最近 20 条 -->
<template>
  <div class="alert-wrapper">
    <div class="alert-header">
      <h4>告警列表</h4>
      <el-button text size="small" @click="alertStore.clearAlerts()" v-if="alertStore.alerts.length > 0">
        清空
      </el-button>
    </div>
    <el-empty v-if="alertStore.alerts.length === 0" description="✅ 无告警" :image-size="60" />
    <el-table
      v-else
      :data="alertStore.alerts"
      size="small"
      max-height="35vh"
      stripe
      :row-class-name="rowClassName"
    >
      <el-table-column prop="timestamp" label="时间" width="80">
        <template #default="{ row }">
          {{ formatTime(row.timestamp) }}
        </template>
      </el-table-column>
      <el-table-column prop="severity" label="级别" width="80">
        <template #default="{ row }">
          <el-tag :type="row.severity === 'critical' ? 'danger' : 'warning'" size="small">
            {{ row.severity }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="level" label="类型" width="100" />
      <el-table-column prop="message" label="消息">
        <template #default="{ row }">
          <span class="alert-msg">{{ row.message }}</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { useAlertStore } from '@/stores/alert'

const alertStore = useAlertStore()

function formatTime(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleTimeString('zh-CN')
  } catch {
    return timestamp
  }
}

// 新告警首行高亮（依靠 CSS animation）
function rowClassName({ rowIndex }: { rowIndex: number }) {
  return rowIndex === 0 ? 'alert-new-row' : ''
}
</script>

<style scoped>
.alert-wrapper {
  background: #0f0f1a;
  border-radius: 4px;
  padding: 12px;
  min-height: 150px;
}
.alert-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.alert-header h4 {
  margin: 0;
  color: #e0e0e0;
  font-size: 14px;
}
.alert-msg {
  display: block;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.alert-new-row) {
  animation: highlight-fade 2s ease-out;
}
@keyframes highlight-fade {
  0% { background-color: rgba(230, 162, 60, 0.3); }
  100% { background-color: transparent; }
}
</style>
