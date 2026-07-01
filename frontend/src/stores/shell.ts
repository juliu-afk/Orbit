import { defineStore } from 'pinia'; import { ref } from 'vue'; import type { ChatMessage } from '@/stores/chat';
export const useShellStore = defineStore('shell', () => {
  const showFileTree = ref(true); const showMonaco = ref(false); const showDAG = ref(false);
  const showChart = ref(false); const showSearch = ref(false); const selectedFile = ref<string | null>(null);
  const quoteTarget = ref<ChatMessage | null>(null);
  function toggleFileTree() { showFileTree.value = !showFileTree.value }
  function openFileReview(path: string) { selectedFile.value = path; showMonaco.value = true }
  function closeFileReview() { showMonaco.value = false; selectedFile.value = null }
  function setQuoteTarget(msg: ChatMessage | null) { quoteTarget.value = msg }
  function toggleDAG() { showDAG.value = !showDAG.value; if (showDAG.value) { showChart.value = false; showSearch.value = false } }
  function toggleChart() { showChart.value = !showChart.value; if (showChart.value) { showDAG.value = false; showSearch.value = false } }
  function toggleSearch() { showSearch.value = !showSearch.value; if (showSearch.value) { showDAG.value = false; showChart.value = false } }
  function closeAllDrawers() { showDAG.value = false; showChart.value = false; showSearch.value = false }
  return { showFileTree, showMonaco, showDAG, showChart, showSearch, selectedFile, quoteTarget, toggleFileTree, openFileReview, closeFileReview, setQuoteTarget, toggleDAG, toggleChart, toggleSearch, closeAllDrawers }
})
