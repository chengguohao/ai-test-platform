import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'projects', component: () => import('@/views/ProjectList.vue'), meta: { title: '项目列表' } },
  { path: '/project/:id', name: 'workflow', component: () => import('@/views/WorkflowBoard.vue'), meta: { title: '工作台' }, props: true },
  { path: '/project/:id/designer', name: 'designer', component: () => import('@/views/FlowDesigner.vue'), meta: { title: '模板设计' }, props: true },
  { path: '/project/:id/report', name: 'report', component: () => import('@/views/ExecutionReport.vue'), meta: { title: '执行报告' }, props: true },
  { path: '/skills', name: 'skills', component: () => import('@/views/SkillCenter.vue'), meta: { title: 'Skill 能力' } },
  { path: '/ai-models', name: 'ai-models', component: () => import('@/views/AiModelSettings.vue'), meta: { title: 'AI 配置' } },
  { path: '/connectors', name: 'connectors', component: () => import('@/views/ConnectorSettings.vue'), meta: { title: '连接器设置' } },
  { path: '/knowledge', name: 'knowledge', component: () => import('@/views/Knowledge.vue'), meta: { title: '知识库' } },
  { path: '/usage', name: 'usage', component: () => import('@/views/UsageGuide.vue'), meta: { title: '使用说明' } },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.afterEach((to) => {
  document.title = to.meta?.title ? `${to.meta.title} · AI 测试工作流平台` : 'AI 测试工作流平台'
})

export default router
