<!-- Cytoscape 图谱画布——渲染 + 交互核心。
     WHY 直接操作 cytoscape instance 而非 Vue 响应式封装：
     Cytoscape 内部状态（位置/缩放/样式）变更频繁（60fps），
     过 Vue 响应式会触发不必要的组件重渲染。仅在选中/过滤状态变更时写 store。 -->
<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import cytoscape, { type Core } from 'cytoscape'
import { useCodeGraphStore } from '@/stores/codegraph'

const store = useCodeGraphStore()
const containerRef = ref<HTMLElement | null>(null)
let cy: Core | null = null

// ── 初始化 ──
onMounted(async () => {
  await nextTick()
  if (!containerRef.value) return

  cy = cytoscape({
    container: containerRef.value,
    style: [
      // 默认节点样式——按类型区分颜色
      { selector: 'node',
        style: { 'background-color': '#3b82f6', 'label': 'data(label)',
                 'color': '#e0e0e0', 'font-size': '11px', 'text-valign': 'center',
                 'text-halign': 'center', 'width': 40, 'height': 40 } },
      { selector: 'node[type="file"]', style: { 'background-color': '#6366f1', 'shape': 'rectangle', 'width': 60, 'height': 30 } },
      { selector: 'node[type="function"]', style: { 'background-color': '#3b82f6', 'shape': 'ellipse' } },
      { selector: 'node[type="class"]', style: { 'background-color': '#8b5cf6', 'shape': 'hexagon' } },
      { selector: 'node:selected', style: { 'border-width': 3, 'border-color': '#f59e0b' } },
      // 边
      { selector: 'edge', style: { 'width': 1.5, 'line-color': '#475569', 'target-arrow-color': '#475569',
                                    'target-arrow-shape': 'triangle', 'curve-style': 'bezier' } },
      { selector: 'edge[type="imports"]', style: { 'line-color': '#6366f1', 'target-arrow-color': '#6366f1' } },
      { selector: 'edge[type="calls"]', style: { 'line-color': '#3b82f6', 'target-arrow-color': '#3b82f6' } },
      { selector: 'edge[type="inherits"]', style: { 'line-color': '#8b5cf6', 'target-arrow-color': '#8b5cf6' } },
    ],
    layout: { name: 'cose', animate: true, animationDuration: 800 } as cytoscape.LayoutOptions,
    // 交互
    wheelSensitivity: 0.3,
    minZoom: 0.1, maxZoom: 3,
  })

  // 点击事件——选中节点
  cy.on('tap', 'node', (evt) => {
    const node = evt.target
    store.selectNode(node.id())
    // 高亮邻居 + 其余半透明
    const c = cy!  // TS 窄化——onMounted 后 cy 一定非 null
    const neighborhood = node.closedNeighborhood()
    c.nodes().forEach((n: cytoscape.NodeSingular) => { n.style('opacity', '0.3') })
    c.edges().forEach((e: cytoscape.EdgeSingular) => { e.style('opacity', '0.15') })
    neighborhood.forEach((el: cytoscape.NodeSingular | cytoscape.EdgeSingular) => { el.style('opacity', '1') })
  })

  // 双击空白——重置
  cy.on('dbltap', (evt) => {
    if (evt.target === cy) {
      store.selectNode(null)
      const c = cy!
      c.nodes().forEach((n: cytoscape.NodeSingular) => { n.style('opacity', '1') })
      c.edges().forEach((e: cytoscape.EdgeSingular) => { e.style('opacity', '1') })
    }
  })

  // 监听窗口 resize
  const onResize = () => { cy?.resize(); cy?.fit(undefined, 50) }
  window.addEventListener('resize', onResize)
  ;(containerRef.value as HTMLElement & { _resizeCleanup: () => void })._resizeCleanup = () =>
    window.removeEventListener('resize', onResize)

  // 初始加载数据
  if (store.elements.length > 0) {
    cy.json({ elements: store.elements as cytoscape.ElementDefinition[] })
    cy.layout({ name: 'cose', animate: true, animationDuration: 800 } as cytoscape.LayoutOptions).run()
  }
})

// ── 数据更新 ──
watch(() => store.elements, (elems) => {
  if (!cy) return
  // WHY json() 全量替换：比逐条 add/remove 更高效，
  // Cytoscape 内部 diff 减少 DOM 操作
  cy.json({ elements: elems as cytoscape.ElementDefinition[] })
  cy.layout({ name: store.activeLayout, animate: true, animationDuration: 800 } as cytoscape.LayoutOptions).run()
}, { deep: false })

// ── 布局切换 ──
watch(() => store.activeLayout, (layout) => {
  if (!cy || cy.nodes().length === 0) return
  cy.layout({ name: layout, animate: true, animationDuration: 800 } as cytoscape.LayoutOptions).run()
})

// ── 搜索过滤 ──
watch(() => store.searchQuery, (query) => {
  if (!cy) return
  if (!query) {
    cy.nodes().forEach(n => { n.style('opacity', '1'); n.removeClass('search-hit') })
    return
  }
  const lower = query.toLowerCase()
  cy.nodes().forEach(n => {
    const label = (n.data('label') || '').toString().toLowerCase()
    const filePath = (n.data('file_path') || '').toString().toLowerCase()
    if (label.includes(lower) || filePath.includes(lower)) {
      n.style('opacity', '1')
      n.addClass('search-hit')
    } else {
      n.style('opacity', '0.2')
      n.removeClass('search-hit')
    }
  })
})

// ── 清理 ──
onUnmounted(() => {
  if (containerRef.value) {
    const el = containerRef.value as HTMLElement & { _resizeCleanup?: () => void }
    el._resizeCleanup?.()
  }
  cy?.destroy()
  cy = null
})
</script>

<template>
  <div class="cytoscape-canvas" ref="containerRef" />
</template>

<style scoped>
.cytoscape-canvas {
  width: 100%;
  height: 100%;
  min-height: 400px;
  background: #0a0a1a;
  border-radius: 8px;
}
</style>
