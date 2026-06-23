<!-- DAG 拓扑图：vis-network 渲染，节点颜色映射 NodeStatus -->
<template>
  <div class="dag-wrapper">
    <div v-if="!hasNodes" class="dag-empty">
      <el-empty description="暂无运行任务" />
    </div>
    <div ref="containerRef" class="dag-container" :class="{ hidden: !hasNodes }" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Network } from 'vis-network'
import { useTaskStore } from '@/stores/task'

const taskStore = useTaskStore()
const containerRef = ref<HTMLElement | null>(null)
let network: Network | null = null

const hasNodes = computed(() => taskStore.dagNodes.size > 0)

onMounted(() => {
  if (!containerRef.value) return
  // WHY 传纯对象而非 DataSet：vis-network 内部自动包装为 DataSet，
  // 避免类型不兼容问题。更新时用 setData 全量替换。
  network = new Network(
    containerRef.value,
    { nodes: taskStore.visData.nodes as unknown as Record<string, unknown>[],
      edges: taskStore.visData.edges as unknown as Record<string, unknown>[] },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    {
      physics: false,
      layout: {
        hierarchical: {
          enabled: true,
          direction: 'LR',
          sortMethod: 'directed',
          nodeSpacing: 150,
          levelSeparation: 200,
        },
      },
      nodes: {
        shape: 'box',
        font: { size: 12, color: '#e0e0e0' },
        margin: 10,
      },
      edges: {
        smooth: true,
        arrows: { to: { enabled: true } },
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
      },
    } as any
  )

  network.on('click', (params) => {
    if (params.nodes.length > 0) {
      // P1: 点击节点打开详情 Modal
    }
  })
})

watch(
  () => taskStore.visData,
  (data) => {
    if (!network) return
    // WHY setData 全量替换：vis-network 内部做 diff，
    // 比逐条 add/update 更高效且避免状态不一致
    ;(network as any).setData({
      nodes: data.nodes as unknown as Record<string, unknown>[],
      edges: data.edges as unknown as Record<string, unknown>[],
    })
  },
  { deep: true }
)

onUnmounted(() => {
  if (network) {
    network.destroy()
    network = null
  }
})
</script>

<style scoped>
.dag-wrapper {
  width: 100%;
  height: 55vh;
  background: #0f0f1a;
  border-radius: 4px;
  overflow: hidden;
}
.dag-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
.dag-container { width: 100%; height: 100%; }
.dag-container.hidden { visibility: hidden; height: 0; }
</style>
