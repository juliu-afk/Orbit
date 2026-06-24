<!-- 组件健康状态面板：8 核心组件状态网格 -->
<template>
  <div class="health-panel">
    <div class="health-panel__overall">
      系统状态：
      <span :class="overallClass">{{ overallLabel }}</span>
    </div>
    <div class="health-panel__grid">
      <div
        v-for="c in components"
        :key="c.name"
        class="health-panel__item"
        :class="`health-panel__item--${c.status}`"
      >
        <span
          class="health-panel__dot"
          :class="`health-panel__dot--${c.status}`"
          @click="handleComponentClick(c.name)"
          style="cursor: pointer"
        ></span>
        <span class="health-panel__name">{{ c.name }}</span>
        <span v-if="c.message" class="health-panel__msg">{{ c.message }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ComponentHealth } from '@/types/dashboard'

const props = defineProps<{
  components: ComponentHealth[]
  overall: string
}>()

const overallLabel = computed(() => {
  switch (props.overall) {
    case 'healthy': return '健康'
    case 'degraded': return '降级'
    case 'unhealthy': return '异常'
    default: return '未知'
  }
})

const overallClass = computed(() => `health-panel__overall--${props.overall}`)
import { useHealthStore } from '@/stores/health'

const healthStore = useHealthStore()

function handleComponentClick(name: string) {
  healthStore.fetchComponent(name)
}
</script>

<style scoped>
.health-panel { padding: 12px; }
.health-panel__overall {
  font-size: 14px;
  margin-bottom: 12px;
  color: #c0c0c0;
}
.health-panel__overall--healthy { color: #4caf50; font-weight: 700; }
.health-panel__overall--degraded { color: #ff9800; font-weight: 700; }
.health-panel__overall--unhealthy { color: #f44336; font-weight: 700; }

.health-panel__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.health-panel__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #12122a;
  border-radius: 6px;
  border: 1px solid #2a2a4a;
}
.health-panel__dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.health-panel__dot--healthy { background: #4caf50; }
.health-panel__dot--degraded { background: #ff9800; }
.health-panel__dot--unhealthy { background: #f44336; }
.health-panel__dot--unknown { background: #666; }

.health-panel__name {
  font-size: 12px; color: #e0e0e0; flex: 1;
}
.health-panel__msg {
  font-size: 10px; color: #888; max-width: 100px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
