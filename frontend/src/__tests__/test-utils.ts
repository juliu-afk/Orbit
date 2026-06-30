// P2-3 (PR#131): 共享测试 stubs——Element Plus 组件 stub 定义
// 避免 18 个 spec 文件重复定义 el-button、el-empty 等

export const ELEMENT_STUBS = {
  'el-button': {
    template:
      '<button class="el-button-stub" @click="$emit(\'click\', $event)"><slot /></button>',
    props: ['loading', 'disabled'],
  },
  'el-empty': {
    template: '<div class="el-empty-stub"><slot /></div>',
  },
  'el-table': {
    template: '<div class="el-table-stub"><slot /></div>',
  },
  'el-table-column': true,
  'el-tag': {
    template: '<span class="el-tag-stub"><slot /></span>',
  },
  'el-card': {
    template: '<div class="el-card-stub"><slot name="header" /><slot /></div>',
  },
  'el-row': {
    template: '<div class="el-row-stub"><slot /></div>',
  },
  'el-col': {
    template: '<div class="el-col-stub"><slot /></div>',
  },
  'el-progress': {
    template: '<div class="el-progress-stub"></div>',
    props: ['percentage'],
  },
}
