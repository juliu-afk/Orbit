<!-- 熔断器状态指示灯：绿=CLOSED / 黄=HALF_OPEN / 红=OPEN -->
<template>
  <div class="cb-light" :title="`${name}: ${stateLabel}`">
    <span class="cb-light__dot" :class="dotClass"></span>
    <span class="cb-light__label">{{ name }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  name: string
  state: number  // 0=CLOSED, 1=OPEN, 2=HALF_OPEN
}>()

const stateLabel = computed(() => {
  switch (props.state) {
    case 0: return 'CLOSED'
    case 1: return 'OPEN'
    case 2: return 'HALF_OPEN'
    default: return 'UNKNOWN'
  }
})

const dotClass = computed(() => ({
  'cb-light__dot--closed': props.state === 0,
  'cb-light__dot--open': props.state === 1,
  'cb-light__dot--half-open': props.state === 2,
}))
</script>

<style scoped>
.cb-light {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #16163a;
  border-radius: 16px;
  border: 1px solid #2a2a5a;
}
.cb-light__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #666;
}
.cb-light__dot--closed { background: #4caf50; box-shadow: 0 0 6px #4caf50; }
.cb-light__dot--open { background: #f44336; box-shadow: 0 0 6px #f44336; }
.cb-light__dot--half-open { background: #ff9800; box-shadow: 0 0 6px #ff9800; }
.cb-light__label {
  font-size: 12px;
  color: #c0c0c0;
}
</style>
