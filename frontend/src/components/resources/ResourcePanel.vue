<!-- 资源视图：队列柱状图 + 工具排行 + 配额仪表 -->
<template>
  <div class="resource-panel">
    <el-row :gutter="12">
      <!-- 调度队列 -->
      <el-col :xs="24" :lg="14">
        <el-card shadow="never" class="panel-card">
          <template #header>调度队列</template>
          <div class="queue-chart">
            <div v-for="p in priorities" :key="p.key" class="queue-bar-col">
              <div class="queue-bar-label">{{ p.label }}</div>
              <div
                class="queue-bar"
                :class="`queue-bar--${p.key}`"
                :style="{ height: barHeight(opsStore.queueStatus[p.key]) + 'px' }"
              >
                <span v-if="opsStore.queueStatus[p.key] > 0" class="queue-bar-num">
                  {{ opsStore.queueStatus[p.key] }}
                </span>
              </div>
            </div>
          </div>
          <div class="queue-summary">
            活跃任务: {{ opsStore.queueStatus.active }}
            <span v-if="totalQueued === 0" style="color:#4caf50"> ✅ 无排队</span>
          </div>
        </el-card>
      </el-col>

      <!-- 工具排行 -->
      <el-col :xs="24" :lg="10">
        <el-card shadow="never" class="panel-card">
          <template #header>工具调用 Top 5</template>
          <div v-if="opsStore.toolStats.length === 0" class="empty-hint">尚无调用记录</div>
          <div v-else class="tool-list">
            <div v-for="(t, i) in opsStore.toolStats.slice(0, 5)" :key="t.tool_name" class="tool-item">
              <span class="tool-item__rank">{{ i + 1 }}</span>
              <span class="tool-item__name">{{ t.tool_name }}</span>
              <span class="tool-item__count">{{ t.count }} 次</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useResourcesStore } from '@/stores/resources'

const opsStore = useResourcesStore()

const priorities = [
  { key: 'critical' as const, label: 'CRITICAL' },
  { key: 'high' as const, label: 'HIGH' },
  { key: 'normal' as const, label: 'NORMAL' },
  { key: 'low' as const, label: 'LOW' },
]

const totalQueued = computed(() =>
  opsStore.queueStatus.critical + opsStore.queueStatus.high +
  opsStore.queueStatus.normal + opsStore.queueStatus.low
)

function barHeight(count: number): number {
  return Math.min(count * 20, 120)
}
</script>

<style scoped>
.resource-panel { padding: 12px; }
.panel-card { margin-bottom: 12px; background: #12122a; border: 1px solid #2a2a4a; }
.panel-card :deep(.el-card__header) {
  border-bottom: 1px solid #2a2a4a; color: #c0c0c0; font-size: 14px;
}
.empty-hint { text-align: center; padding: 24px; color: #666; }

.queue-chart { display: flex; gap: 24px; justify-content: center; align-items: flex-end; padding: 20px; min-height: 150px; }
.queue-bar-col { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.queue-bar-label { font-size: 11px; color: #888; }
.queue-bar {
  width: 40px; min-height: 4px; border-radius: 4px 4px 0 0;
  background: #444; transition: height 0.3s;
  display: flex; align-items: flex-start; justify-content: center;
}
.queue-bar--critical { background: #f44336; }
.queue-bar--high { background: #ff9800; }
.queue-bar--normal { background: #2196f3; }
.queue-bar--low { background: #666; }
.queue-bar-num { font-size: 12px; color: #fff; padding-top: 2px; }

.queue-summary { text-align: center; font-size: 13px; color: #c0c0c0; padding: 8px; }

.tool-item {
  display: flex; gap: 12px; align-items: center; padding: 8px 12px;
  border-bottom: 1px solid #1a1a3a; font-size: 13px;
}
.tool-item__rank {
  width: 20px; height: 20px; border-radius: 50%;
  background: #1a3a5c; color: #4caf50; text-align: center; line-height: 20px;
  font-size: 11px; font-weight: 700;
}
.tool-item__name { flex: 1; color: #e0e0e0; }
.tool-item__count { color: #888; }
</style>
