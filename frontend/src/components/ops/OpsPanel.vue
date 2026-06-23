<!-- 运维面板：当前版本 + 备份 + 版本时间线 + SOP -->
<template>
  <div class="ops-panel">
    <div class="ops-version">
      当前版本: <span class="ops-version__badge">{{ opsStore.currentVersion || '---' }}</span>
    </div>

    <el-row :gutter="12">
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>备份快照</template>
          <div v-if="opsStore.snapshots.length === 0" class="empty-hint">暂无快照</div>
          <div v-else class="snap-list">
            <div v-for="s in opsStore.snapshots" :key="s.name" class="snap-item">
              <span>{{ s.name }}</span>
              <span>{{ s.size_mb }} MB</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>发布历史</template>
          <div v-if="opsStore.releases.length === 0" class="empty-hint">尚无发布记录</div>
          <div v-else class="timeline">
            <div v-for="r in opsStore.releases.slice(0, 10)" :key="r.timestamp" class="timeline-item" :class="`timeline-item--${r.event_type}`">
              <span class="timeline-item__ver">{{ r.version }}</span>
              <span class="timeline-item__type">{{ eventLabel(r.event_type) }}</span>
              <span class="timeline-item__trigger">{{ r.trigger }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="panel-card" style="margin-top:12px">
      <template #header>SOP 灾难恢复手册</template>
      <div v-if="opsStore.sopContent" class="sop-content" v-html="renderedSop"></div>
      <div v-else class="empty-hint">手册加载中...</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useOpsStore } from '@/stores/ops'

const opsStore = useOpsStore()

function eventLabel(type: string): string {
  const map: Record<string, string> = {
    deploy: '部署', rollback: '回滚', canary_start: '金丝雀开始', canary_end: '金丝雀结束',
  }
  return map[type] || type
}

// 简单 Markdown 渲染 (标题/bold 支持)
const renderedSop = computed(() => {
  let html = opsStore.sopContent
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
  return html
})
</script>

<style scoped>
.ops-panel { padding: 12px; color: #e0e0e0; }
.ops-version { font-size: 14px; margin-bottom: 12px; color: #c0c0c0; }
.ops-version__badge {
  background: #1a3a5c; padding: 2px 10px; border-radius: 12px;
  font-weight: 700; color: #4caf50;
}
.panel-card { margin-bottom: 12px; background: #12122a; border: 1px solid #2a2a4a; }
.panel-card :deep(.el-card__header) {
  border-bottom: 1px solid #2a2a4a; color: #c0c0c0; font-size: 14px;
}
.empty-hint { text-align: center; padding: 24px; color: #666; font-size: 13px; }

.timeline-item {
  display: flex; gap: 12px; padding: 6px 0; border-bottom: 1px solid #1a1a3a;
  font-size: 12px;
}
.timeline-item--deploy { border-left: 3px solid #4caf50; padding-left: 8px; }
.timeline-item--rollback { border-left: 3px solid #f44336; padding-left: 8px; }
.timeline-item__ver { font-weight: 600; }
.timeline-item__type { color: #8888aa; }
.timeline-item__trigger { color: #6666aa; margin-left: auto; }

.sop-content { font-size: 13px; line-height: 1.6; }
.sop-content h2, .sop-content h3 { color: #4caf50; margin: 12px 0 4px; }
.sop-content code { background: #16163a; padding: 1px 4px; border-radius: 3px; }
</style>
