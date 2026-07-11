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
            <div v-for="s in opsStore.snapshots" :key="s.snapshot_id" class="snap-item">
              <span class="snap-path">{{ s.path }}</span>
              <span class="snap-size">{{ (s.size_bytes / 1048576).toFixed(1) }} MB</span>
              <el-button size="small" type="warning" text :loading="restoringId === s.snapshot_id" @click="onRestore(s)">恢复</el-button>
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
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useOpsStore, type SnapshotItem } from '@/stores/ops'

const opsStore = useOpsStore()
const restoringId = ref('')

// db_type → 默认恢复目标路径（按后端约定预填，用户可在弹窗中修改确认）
const DEFAULT_TARGETS: Record<string, string> = {
  sqlite: 'data/orbit.db',
  knowledge: 'data/knowledge.db',
  checkpoint: 'data/checkpoint.db',
}

// PR9: 在线恢复——安全性高（覆盖生产数据）。护栏：
// ① 显式 target 输入让用户确认覆盖对象 ② 二次确认弹窗
// ③ 后端 Restorer 覆盖前自动备份 .backup 且校验失败自动回滚（双保险）
async function onRestore(s: SnapshotItem) {
  const defaultTarget = DEFAULT_TARGETS[s.db_type] || s.path
  let targetPath: string
  try {
    const { value } = await ElMessageBox.prompt(
      `将从快照恢复到目标文件（会覆盖现有数据）。请确认目标路径：`,
      '恢复目标',
      { inputValue: defaultTarget, confirmButtonText: '下一步', cancelButtonText: '取消' },
    )
    targetPath = (value || '').trim()
    if (!targetPath) { ElMessage.warning('目标路径不能为空'); return }
  } catch { return }  // 用户取消

  try {
    await ElMessageBox.confirm(
      `确认用快照 ${s.snapshot_id.slice(0, 8)} 覆盖 ${targetPath}？\n此操作会覆盖现有数据（后端自动备份为 .backup，校验失败自动回滚）。`,
      '二次确认——危险操作',
      { confirmButtonText: '确认恢复', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }

  restoringId.value = s.snapshot_id
  try {
    await opsStore.restoreSnapshot(s.snapshot_id, targetPath)
    ElMessage.success(`已恢复到 ${targetPath}`)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '恢复失败')
  } finally {
    restoringId.value = ''
  }
}

function eventLabel(type: string): string {
  const map: Record<string, string> = {
    deploy: '部署', rollback: '回滚', canary_start: '金丝雀开始', canary_end: '金丝雀结束',
  }
  return map[type] || type
}

// 简单 Markdown 渲染 (标题/bold 支持)
// P0-17 (Issue#126): 先转义 HTML 实体防 XSS，再应用 Markdown 替换
const renderedSop = computed(() => {
  // P0-2 (PR#131): sopContent 可能为 null/undefined——初始加载时
  const raw = opsStore.sopContent || ''
  let html = raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
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

.snap-list { display: flex; flex-direction: column; }
.snap-item { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid #1a1a3a; font-size: 12px; }
.snap-path { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #c0c0c0; }
.snap-size { color: #8888aa; white-space: nowrap; }

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
