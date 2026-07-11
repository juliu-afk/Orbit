import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { ref } from 'vue'

// ── Mock vue-router ─────────────────────────────────────────────────────
vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => ({ params: { taskId: 'task-abc-123' } })),
}))

// ── Mock Pinia stores ───────────────────────────────────────────────────

const mockReviewStatus = ref('in_review')
const mockReviewDecisions = ref<any[]>([])
const mockReviewCreateReview = vi.fn()
const mockTransitionStatus = vi.fn()

vi.mock('@/stores/review', () => ({
  useReviewStore: vi.fn(() => ({
    reviewId: ref('review-1'),
    taskId: ref('task-abc-123'),
    status: mockReviewStatus,
    decisions: mockReviewDecisions,
    comments: ref([]),
    loading: ref(false),
    createReview: mockReviewCreateReview,
    transitionStatus: mockTransitionStatus,
    recordDecision: vi.fn(),
  })),
}))

const mockCurrentFile = ref<string | null>(null)
const mockOriginal = ref('')
const mockModified = ref('')
const mockLanguage = ref('python')
const mockOpenFile = vi.fn()

vi.mock('@/stores/editor', () => ({
  useEditorStore: vi.fn(() => ({
    currentFile: mockCurrentFile,
    original: mockOriginal,
    modified: mockModified,
    language: mockLanguage,
    loading: ref(false),
    openFile: mockOpenFile,
  })),
}))

const mockDiagnosticsList = ref<any[]>([])

vi.mock('@/stores/diagnostics', () => ({
  useDiagnosticsStore: vi.fn(() => ({
    diagnostics: mockDiagnosticsList,
    loading: ref(false),
    fetchDiagnostics: vi.fn(),
  })),
}))

const mockGpgKeys = ref<any[]>([])
const mockCommitting = ref(false)
const mockCommit = vi.fn()

vi.mock('@/stores/gitStore', () => ({
  useGitStore: vi.fn(() => ({
    gpgKeys: mockGpgKeys,
    committing: mockCommitting,
    fetchGpgKeys: vi.fn(),
    commit: mockCommit,
  })),
}))

// ── Mock API service ────────────────────────────────────────────────────
vi.mock('@/services/api', () => ({
  apiGet: vi.fn().mockResolvedValue({ files: [] }),
  apiPost: vi.fn(),
}))

// ── End mocks ───────────────────────────────────────────────────────────

import ReviewView from '@/views/ReviewView.vue'

// 全局 mock: $router.push 在模板中直接使用
const mockRouterPush = vi.fn()

// Element Plus + child component stubs
const stubs = {
  'el-button': { name: 'ElButton', template: '<button class="el-button-stub" @click="$emit(\'click\')"><slot /></button>' },
  'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
  'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
  'el-empty': { template: '<div class="el-empty-stub"><slot /></div>' },
  'el-tabs': { template: '<div class="el-tabs-stub"><slot /></div>' },
  'el-tab-pane': { template: '<div class="el-tab-pane-stub"><slot /></div>' },
  'el-dialog': { template: '<div class="el-dialog-stub" v-if="modelValue"><slot /></div>', props: ['modelValue'] },
  'el-input': { template: '<input class="el-input-stub" />' },
  'el-checkbox': { template: '<input type="checkbox" class="el-checkbox-stub" />' },
  'el-select': { template: '<select class="el-select-stub"><slot /></select>' },
  'el-option': { template: '<option class="el-option-stub" />' },
  ArrowLeft: { template: '<span class="arrow-left-stub" />' },
  MonacoDiffEditor: { name: 'MonacoDiffEditor', template: '<div class="monaco-diff-stub" />' },
  FileTreePanel: { name: 'FileTreePanel', template: '<div class="file-tree-stub" />' },
  ProblemPanel: { template: '<div class="problem-panel-stub" />' },
}

describe('ReviewView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockReviewStatus.value = 'in_review'
    mockCurrentFile.value = null
    mockReviewDecisions.value = []
    mockRouterPush.mockReset()
  })

  it('renders toolbar with Back button', () => {
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    expect(wrapper.find('.review-toolbar').exists()).toBe(true)
    expect(wrapper.text()).toContain('Back')
  })

  it('shows task id in toolbar', () => {
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    expect(wrapper.text()).toContain('Task:')
    // task-abc-123 sliced to first 8 chars → task-abc
    expect(wrapper.text()).toContain('task-abc')
  })

  it('shows status tag reflecting current review status', () => {
    mockReviewStatus.value = 'in_review'
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    expect(wrapper.text()).toContain('In Review')
  })

  it('shows "Approved" status tag when approved', () => {
    mockReviewStatus.value = 'approved'
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    expect(wrapper.text()).toContain('Approved')
  })

  it('shows no-file empty state when no file is selected', () => {
    mockCurrentFile.value = null
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    const noFile = wrapper.find('.no-file')
    expect(noFile.exists()).toBe(true)
    expect(noFile.text()).toContain('Select a file')
  })

  it('renders MonacoDiffEditor when a file is selected', () => {
    mockCurrentFile.value = 'src/main.py'
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    expect(wrapper.find('.no-file').exists()).toBe(false)
    // MonacoDiffEditor is stubbed via global.stubs + shallowMount
    expect(wrapper.findComponent({ name: 'MonacoDiffEditor' }).exists()).toBe(true)
  })

  it('renders FileTreePanel in sidebar', () => {
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    expect(wrapper.find('.review-sidebar').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'FileTreePanel' }).exists()).toBe(true)
  })

  it('shows Commit button when status is approved', () => {
    mockReviewStatus.value = 'approved'
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    const buttons = wrapper.findAllComponents({ name: 'ElButton' })
    const commitBtn = buttons.find((b) => b.text().includes('Commit'))
    expect(commitBtn).toBeTruthy()
  })

  it('does NOT show Commit button when status is not approved', () => {
    mockReviewStatus.value = 'in_review'
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    expect(wrapper.text()).not.toContain('Commit')
  })

  it('shows Approve All and Reject All buttons when in_review', () => {
    mockReviewStatus.value = 'in_review'
    const wrapper = shallowMount(ReviewView, {
      global: { stubs, mocks: { $router: { push: mockRouterPush } } },
    })
    expect(wrapper.text()).toContain('Approve All')
    expect(wrapper.text()).toContain('Reject All')
  })
})
