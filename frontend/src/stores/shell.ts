import { defineStore } from 'pinia'; import { ref } from 'vue'; import type { ChatMessage } from '@/stores/chat';
export const useShellStore = defineStore('shell', () => {
  const showFileTree = ref(true); const showMonaco = ref(false); const showDAG = ref(false);
  const showChart = ref(false); const showSearch = ref(false); const showSchedule = ref(false);
  const showTrace = ref(false); const showConfig = ref(false);
  const showCodeGraph = ref(false); const showWeChat = ref(false); const showBranches = ref(false);
  const selectedFile = ref<string | null>(null);
  const quoteTarget = ref<ChatMessage | null>(null);
  function toggleFileTree() { showFileTree.value = !showFileTree.value }
  function openFileReview(path: string) { selectedFile.value = path; showMonaco.value = true }
  function closeFileReview() { showMonaco.value = false; selectedFile.value = null }
  function setQuoteTarget(msg: ChatMessage | null) { quoteTarget.value = msg }
  function toggleDAG() { showDAG.value = !showDAG.value; if (showDAG.value) { showChart.value = false; showSearch.value = false } }
  function toggleChart() { showChart.value = !showChart.value; if (showChart.value) { showDAG.value = false; showSearch.value = false } }
  function toggleSearch() { showSearch.value = !showSearch.value; if (showSearch.value) { showDAG.value = false; showChart.value = false } }
  function toggleSchedule() { showSchedule.value = !showSchedule.value; if (showSchedule.value) { showDAG.value = false; showChart.value = false; showSearch.value = false } }
  function toggleTrace() { showTrace.value = !showTrace.value; if (showTrace.value) { showDAG.value = false; showChart.value = false; showSearch.value = false; showSchedule.value = false } }
  function toggleConfig() { showConfig.value = !showConfig.value; if (showConfig.value) { showDAG.value = false; showChart.value = false; showSearch.value = false; showSchedule.value = false } }
  function toggleCodeGraph() { showCodeGraph.value = !showCodeGraph.value; if (showCodeGraph.value) { showDAG.value = false; showChart.value = false; showSearch.value = false } }
  function toggleWeChat() { showWeChat.value = !showWeChat.value; if (showWeChat.value) { showDAG.value = false; showChart.value = false; showSearch.value = false } }
  function closeAllDrawers() { showDAG.value = false; showChart.value = false; showSearch.value = false; showSchedule.value = false; showTrace.value = false; showConfig.value = false; showCodeGraph.value = false; showWeChat.value = false; showBranches.value = false }
  return { showFileTree, showMonaco, showDAG, showChart, showSearch, showSchedule, showTrace, showConfig, showCodeGraph, showWeChat, showBranches, selectedFile, quoteTarget, toggleFileTree, openFileReview, closeFileReview, setQuoteTarget, toggleDAG, toggleChart, toggleSearch, toggleSchedule, toggleTrace, toggleConfig, toggleCodeGraph, toggleWeChat, closeAllDrawers }
})
