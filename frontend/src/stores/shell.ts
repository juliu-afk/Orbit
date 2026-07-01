import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage } from '@/stores/chat'

// WHY 新 store：管理 TerminalShell 面板显隐状态，替代旧三路由页面架构。
// 所有面板互斥逻辑集中在这里——Monaco 打开时右面板从 AgentInfoPanel 切为 MonacoPanel；
// DAG/Chart/Search 同时只有一个是 true。

export const useShellStore = defineStore('shell', () => {
  // 面板显隐
  const showFileTree = ref(true)
  const showMonaco = ref(false)
  const showDAG = ref(false)
  const showChart = ref(false)
  const showSearch = ref(false)

  // 当前文件（代码审查时使用）
  const selectedFile = ref<string | null>(null)

  // 引用目标消息（QuoteChip 使用）
  const quoteTarget = ref<ChatMessage | null>(null)

  // 操作
  function toggleFileTree() {
    showFileTree.value = !showFileTree.value
  }

  function openFileReview(path: string) {
    selectedFile.value = path
    showMonaco.value = true
  }

  function closeFileReview() {
    showMonaco.value = false
    selectedFile.value = null
  }

  function setQuoteTarget(msg: ChatMessage | null) {
    quoteTarget.value = msg
  }

  // 浮层互斥——打开一个关闭其他
  function toggleDAG() {
    showDAG.value = !showDAG.value
    if (showDAG.value) {
      showChart.value = false
      showSearch.value = false
    }
  }

  function toggleChart() {
    showChart.value = !showChart.value
    if (showChart.value) {
      showDAG.value = false
      showSearch.value = false
    }
  }

  function toggleSearch() {
    showSearch.value = !showSearch.value
    if (showSearch.value) {
      showDAG.value = false
      showChart.value = false
    }
  }

  function closeAllDrawers() {
    showDAG.value = false
    showChart.value = false
    showSearch.value = false
  }

  return {
    showFileTree,
    showMonaco,
    showDAG,
    showChart,
    showSearch,
    selectedFile,
    quoteTarget,
    toggleFileTree,
    openFileReview,
    closeFileReview,
    setQuoteTarget,
    toggleDAG,
    toggleChart,
    toggleSearch,
    closeAllDrawers,
  }
})
