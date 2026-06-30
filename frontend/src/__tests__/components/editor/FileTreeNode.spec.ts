import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FileTreeNode from '@/components/editor/FileTreeNode.vue'

const fileNode = { name: 'app.ts', path: '/src/app.ts', isDir: false }
const dirNode = {
  name: 'src',
  path: '/src',
  isDir: true,
  children: [{ name: 'utils.ts', path: '/src/utils.ts', isDir: false }],
}
const approvedNode = { ...fileNode, reviewStatus: 'approved' as const }

describe('FileTreeNode', () => {
  it('renders file node without is-dir class', () => {
    const wrapper = mount(FileTreeNode, {
      props: { node: fileNode, selected: null, depth: 0 },
    })
    expect(wrapper.find('.is-dir').exists()).toBe(false)
    expect(wrapper.text()).toContain('app.ts')
  })

  it('renders directory node with is-dir class', () => {
    const wrapper = mount(FileTreeNode, {
      props: { node: dirNode, selected: null, depth: 0 },
    })
    expect(wrapper.find('.is-dir').exists()).toBe(true)
    expect(wrapper.text()).toContain('src')
  })

  it('click on directory toggles expanded', async () => {
    const wrapper = mount(FileTreeNode, {
      props: { node: dirNode, selected: null, depth: 0 },
    })
    // initially collapsed — children not rendered
    expect(wrapper.text()).not.toContain('utils.ts')
    // expand
    await wrapper.find('.tree-node').trigger('click')
    expect(wrapper.text()).toContain('utils.ts')
    // collapse
    await wrapper.find('.tree-node').trigger('click')
    expect(wrapper.text()).not.toContain('utils.ts')
  })

  it('click on file emits select with path', async () => {
    const wrapper = mount(FileTreeNode, {
      props: { node: fileNode, selected: null, depth: 0 },
    })
    await wrapper.find('.tree-node').trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual(['/src/app.ts'])
  })

  it('shows status dot with correct class for approved', () => {
    const wrapper = mount(FileTreeNode, {
      props: { node: approvedNode, selected: null, depth: 0 },
    })
    expect(wrapper.find('.status-dot.status-approved').exists()).toBe(true)
  })

  it('does not apply status class when reviewStatus is null', () => {
    const wrapper = mount(FileTreeNode, {
      props: { node: fileNode, selected: null, depth: 0 },
    })
    expect(wrapper.find('.status-dot').exists()).toBe(true)
    expect(wrapper.find('.status-approved').exists()).toBe(false)
  })
})
