<!-- 大纲视图——文件函数/类列表 -->
<template>
  <div class="outline-panel">
    <div class="outline-header">Outline</div>
    <div v-if="!items.length" class="outline-empty">No symbols</div>
    <div v-for="(item, i) in items" :key="`${item.kind}:${item.name}:${item.line}:${i}`" class="outline-item"
      :class="'kind-' + item.kind" :style="{ paddingLeft: item.kind === 'method' ? 20 : 8 + 'px' }"
      @click="$emit('select', item.line)">
      <span class="outline-icon">{{ item.kind === 'class' ? 'C' : item.kind === 'method' ? 'M' : 'F' }}</span>
      <span class="outline-name">{{ item.name }}</span>
      <span class="outline-line">:{{ item.line }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface OutlineItem { name: string; kind: string; line: number; children?: OutlineItem[] }
defineProps<{ items: OutlineItem[] }>()
defineEmits<{ (e: 'select', line: number): void }>()
</script>

<style scoped>
.outline-panel { height: 100%; overflow-y: auto; font-size: 13px; }
.outline-header { padding: 8px 12px; font-weight: 600; border-bottom: 1px solid var(--el-border-color-light); }
.outline-empty { padding: 12px; color: var(--el-text-color-secondary); }
.outline-item { display: flex; align-items: center; gap: 4px; padding: 2px 8px; cursor: pointer; }
.outline-item:hover { background: var(--el-fill-color-light); }
.outline-icon { font-size: 10px; width: 16px; text-align: center; color: var(--el-color-primary); flex-shrink: 0; }
.outline-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.outline-line { color: var(--el-text-color-placeholder); font-size: 11px; flex-shrink: 0; }
</style>
