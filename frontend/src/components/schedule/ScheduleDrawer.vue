<script setup lang="ts">
import { watch, ref } from 'vue'
import { usePeakStore } from '@/stores/peak'
import type { DeferredTaskItem } from '@/stores/peak'
import { formatTime, formatDuration } from '@/utils/time'

const visible = defineModel<boolean>('visible', { required: true })
const peak = usePeakStore()
const tab = ref<'queue'|'savings'>('queue')
watch(visible, v => { if (v) peak.refreshAll() })

function safeToFixed(n: number | undefined, digits: number): string { if (n == null || isNaN(n)) return '0.' + '0'.repeat(digits); return n.toFixed(digits) }
async function promote(t: DeferredTaskItem) { try { await peak.promoteToUrgent(t.goal_id) } catch { /* */ } }
</script>

<template>
  <el-drawer v-model="visible" title="高峰避让调度" direction="rtl" size="400px">
    <div :style="{display:'flex',alignItems:'center',gap:'8px',padding:'10px 12px',borderRadius:'6px',background:peak.isPeak?'rgba(230,162,60,.12)':'var(--color-orbit-surface,#1a1a2e)',color:peak.isPeak?'#e6a23c':'',marginBottom:'12px'}">
      <span :style="{width:'8px',height:'8px',borderRadius:'50%',background:peak.isPeak?'#e6a23c':'#67c23a'}" />
      {{ peak.isPeak ? '高峰期' : '低峰期' }}
      <span v-if="peak.queuedCount>0" style="margin-left:auto;font-size:12px;opacity:.8">{{ peak.queuedCount }} 个任务排队中</span>
    </div>
    <el-tabs v-model="tab">
      <el-tab-pane label="排队队列" name="queue">
        <div v-if="peak.queued.length===0" style="text-align:center;color:#888;padding:32px 0">无排队任务</div>
        <div v-else style="display:flex;flex-direction:column;gap:8px">
          <div v-for="t in peak.queued" :key="t.goal_id" style="padding:10px 12px;border-radius:6px;background:var(--color-orbit-surface,#1a1a2e)">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px">
              <span style="font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:220px">{{ t.description || t.goal_id.slice(0,8) }}</span>
              <el-tag size="small" :type="t.priority==='CRITICAL'?'danger':'info'">{{ t.priority }}</el-tag>
            </div>
            <div style="display:flex;gap:12px;font-size:12px;color:#888;margin-bottom:6px">
              <span>{{ t.provider }}</span><span>预计 {{ formatDuration(t.estimated_duration_seconds) }}</span><span>{{ formatTime(t.target_window_start) }}</span>
            </div>
            <div style="text-align:right"><el-button size="small" text type="warning" @click="promote(t)">立即执行</el-button></div>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="成本节省" name="savings">
        <div v-if="!peak.savings" style="text-align:center;color:#888;padding:32px 0">暂无数据</div>
        <div v-else style="display:flex;flex-direction:column;gap:8px">
          <div v-for="s in [{l:'延后任务',v:peak.savings.total_tasks_deferred},{l:'低峰 Token',v:safeToFixed(peak.savings.total_tokens_offpeak/1000,0)+'K'},{l:'累计节省',v:'¥'+safeToFixed(peak.savings.total_saved_yuan,2),hl:true}]" :key="s.l"
            :style="{display:'flex',justifyContent:'space-between',padding:'10px 12px',borderRadius:'6px',background:s.hl?'rgba(103,194,58,.1)':'var(--color-orbit-surface,#1a1a2e)'}">
            <span style="font-size:13px;color:#888">{{ s.l }}</span><span style="font-size:16px;font-weight:600">{{ s.v }}</span>
          </div>
          <el-divider />
          <div v-for="p in peak.savings.by_provider" :key="p.provider" style="display:flex;justify-content:space-between;font-size:13px;padding:4px 0">
            <span>{{ p.provider }}</span><span>{{ p.tasks }} 任务</span><span>¥{{ safeToFixed(p.saved_yuan, 2) }}</span>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>
