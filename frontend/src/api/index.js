/**
 * 后端 API 契约封装（对齐 frontend/SPEC.md 第 3 节）
 * Base = /api（见 http.js）
 */
import http from './http'

/* LLM 生成类接口耗时可达数分钟（自动化脚本生成实测 5 分钟+），
   全局 5 分钟超时会让前端提前断开：后端仍在跑并完成落库，
   但前端拿不到响应（表现为"一直不出内容，刷新页面才有"）。
   这里对 LLM 接口单独放宽到 15 分钟。 */
const LLM_TIMEOUT = 900000

/* ---------------- 项目 ---------------- */
export const projectApi = {
  list: (folderId) => http.get('/projects', { params: folderId != null ? { folder_id: folderId } : {} }),
  get: (id) => http.get(`/projects/${id}`),
  create: (data) => http.post('/projects', data),
  update: (id, data) => http.put(`/projects/${id}`, data),
  copy: (id) => http.post(`/projects/${id}/copy`),
  remove: (id) => http.delete(`/projects/${id}`)
}

/* ---------------- 目录树文件夹 ---------------- */
export const folderApi = {
  tree: () => http.get('/folders'),
  create: (data) => http.post('/folders', data),
  update: (id, data) => http.put(`/folders/${id}`, data),
  remove: (id) => http.delete(`/folders/${id}`)
}

/* ---------------- 工作流 ---------------- */
export const workflowApi = {
  stageLibrary: () => http.get('/workflow/stage-library'),
  templates: (projectId) => http.get('/workflow/templates', { params: { project_id: projectId } }),
  createTemplate: (data) => http.post('/workflow/templates', data),
  updateTemplate: (id, data) => http.put(`/workflow/templates/${id}`, data),
  deleteTemplate: (id) => http.delete(`/workflow/templates/${id}`),
  createRun: (data) => http.post('/workflow/runs', data),
  runs: (projectId) => http.get('/workflow/runs', { params: { project_id: projectId } }),
  run: (runId) => http.get(`/workflow/runs/${runId}`),
  removeRun: (runId) => http.delete(`/workflow/runs/${runId}`),
  stages: (runId) => http.get(`/workflow/runs/${runId}/stages`),
  patchStage: (runId, stageId, data) => http.patch(`/workflow/runs/${runId}/stages/${stageId}`, data),
  advance: (runId) => http.get(`/workflow/runs/${runId}/advance`)
}

/* ---------------- 工件 ---------------- */
export const artifactApi = {
  list: (runId) => http.get('/artifacts', { params: { run_id: runId } }),
  upload: (formData) =>
    http.post('/artifacts/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  downloadUrl: (id) => `/api/artifacts/${id}/download`,
  remove: (id) => http.delete(`/artifacts/${id}`),
  /**
   * 下载工件为文件：fetch blob 后用 <a download> 触发保存。
   * 不能用 window.open——在 await 之后的回调里开新窗口会被浏览器弹窗拦截（表现为"点了没反应"）。
   * 注意：<a download> 会覆盖后端 Content-Disposition，因此文件名无后缀时需前端自行补全。
   */
  download: async (id, name, filePath) => {
    const blob = await http.get(`/artifacts/${id}/download`, { responseType: 'blob' })
    let fname = name || `artifact-${id}`
    // 显示名无后缀时，从工件存储路径补全扩展名，避免下载文件打不开
    if (!/\.[^./\\]+$/.test(fname) && filePath) {
      const ext = (filePath.match(/(\.[^./\\]+)$/) || [])[1]
      if (ext) fname += ext
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fname
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    return fname
  }
}

/* ---------------- 连接器 ---------------- */
export const connectorApi = {
  kinds: () => http.get('/connectors/kinds'),
  list: (projectId = 0) => http.get('/connectors', { params: { project_id: projectId } }),
  create: (data) => http.post('/connectors', data),
  update: (id, data) => http.put(`/connectors/${id}`, data),
  remove: (id) => http.delete(`/connectors/${id}`),
  fetch: (data) => http.post('/connectors/fetch', data),
  mcpTools: (id) => http.get(`/connectors/mcp/${id}/tools`),
  push: (data) => http.post('/connectors/push', data)
}

/* ---------------- AI ---------------- */
export const aiApi = {
  skills: () => http.get('/ai/skills'),
  skillDetail: (id) => http.get(`/ai/skills/${id}`),
  summary: (runId) => http.post('/ai/summary', { run_id: runId }, { timeout: LLM_TIMEOUT }),
  generateCases: (data) => http.post('/ai/generate-cases', data, { timeout: LLM_TIMEOUT }),
  exportCases: (data) => http.post('/ai/export', data),
  review: (data) => http.post('/ai/review', data),
  regenerate: (data) => http.post('/ai/regenerate', data, { timeout: LLM_TIMEOUT }),
  importReviewed: (formData) =>
    http.post('/ai/import-reviewed', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  caseSets: (runId) => http.get(`/ai/case-sets/${runId}`),
  autoGenerate: (data) => http.post('/ai/auto-generate', data, { timeout: LLM_TIMEOUT }),
  runSkill: (data) => http.post('/ai/run-skill', data, { timeout: LLM_TIMEOUT }),
  /* 长任务「思考过程」步骤轮询：key 形如 case_gen:1 / auto_gen:1 / execute:1 */
  progress: (taskKey) => http.get(`/ai/progress/${encodeURIComponent(taskKey)}`),
  /* 执行失败 AI 修复闭环：分析根因 → 打回 → 自动重跑自动化生成（后台线程，立即返回） */
  autoFix: (data) => http.post('/ai/auto-fix', data),
  /* 一键跑工作流：自动完成 生成用例→评审→自动化→执行→失败修复（后台线程，立即返回） */
  autoRun: (data) => http.post('/ai/auto-run', data),
  /* 流程全部完成后生成 AI 执行总结（force=true 忽略缓存重新生成） */
  runSummary: (runId, force = false) => http.post('/ai/run-summary', { run_id: runId, force }, { timeout: LLM_TIMEOUT })
}

/* ---------------- AI 模型配置（全局多模型） ---------------- */
export const aiModelApi = {
  list: () => http.get('/ai-models'),
  create: (data) => http.post('/ai-models', data),
  update: (id, data) => http.put(`/ai-models/${id}`, data),
  remove: (id) => http.delete(`/ai-models/${id}`),
  test: (id) => http.post(`/ai-models/${id}/test`)
}

/* ---------------- 执行 ---------------- */
export const execApi = {
  envCheck: (projectId) => http.post('/exec/env-check', null, { params: { project_id: projectId } }),
  run: (data) => http.post('/exec/run', data),
  runs: (runId) => http.get(`/exec/runs/${runId}`),
  detail: (executionId) => http.get(`/exec/detail/${executionId}`)
}

/* Allure 报告 URL（经 vite /reports 代理） */
export function allureReportUrl(projectName, runId) {
  return `/reports/${projectName}/${runId}/allure-report/index.html`
}
