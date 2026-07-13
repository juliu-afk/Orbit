import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FileTreePanel from '@/components/editor/FileTreePanel.vue'

const mockTreeData = [
  {
    name: 'src',
    path: '/src',
    isDir: true,
    children: [{ name: 'app.ts', path: '/src/app.ts', isDir: false }],
  },
  { name: 'index.ts', path: '/index.ts', isDir: false },
]

function factory(props = {}) {
  return mount(FileTreePanel, {
    props: { treeData: [], selectedFile: null, currentProjectPath: '', ...props },
    global: {
      stubs: {
        'el-empty': { template: '<div class="el-empty-stub"><slot /></div>' },
        'el-tree': { template: '<div class="el-tree-stub"><slot /></div>' },
        'FileTreeProjectBar': { template: '<div class="ft-project-bar-stub" />' },
        FileTreeNode: {
          props: ['node', 'depth'],
          emits: ['select'],
          template: '<div class="file-tree-node-stub" @click="$emit(\'select\', $props.node)">{{ node.name }}</div>',
        },
      },
    },
  })
}

describe('FileTreePanel', () => {
  it('mounts with treeData prop', () => {
    const wrapper = factory({ treeData: mockTreeData })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.tree-header').text()).toContain('Files')
  })

  it('renders file count on header', () => {
    const wrapper = factory({ treeData: mockTreeData })
    expect(wrapper.find('.file-count').text()).toBe('2')
  })

  it('shows empty state when treeData is empty', () => {
    const wrapper = factory({ treeData: [] })
    expect(wrapper.find('.el-empty-stub').exists()).toBe(true)
  })

  it('renders FileTreeNode stub for each root node', () => {
    const wrapper = factory({ treeData: mockTreeData })
    const stubs = wrapper.findAllComponents({ name: 'FileTreeNode' })
    expect(stubs).toHaveLength(2)
  })

  it('emits select-file when child FileTreeNode emits select', () => {
    const wrapper = factory({ treeData: mockTreeData })
    const firstStub = wrapper.findAllComponents({ name: 'FileTreeNode' })[0]
    // 触发子组件的 select 事件
    firstStub.vm.$emit('select', mockTreeData[0])
    expect(wrapper.emitted('select-file')).toBeTruthy()
    expect(wrapper.emitted('select-file')![0]).toEqual([mockTreeData[0]])
  })
})
