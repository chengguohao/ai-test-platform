# 前端实现规格书（ai-test-platform · Vue3 + Element Plus）

> 本文档是前端的**唯一实现依据**。请严格按照本文档实现整个前端，完成后执行 `npm install && npm run build` 确认能编译通过。

## 1. 技术栈与工程
- Vue 3（`<script setup>`）、Vite、Element Plus、Pinia、Vue Router、Axios
- 目录：`frontend/`（本项目根）
- `package.json` scripts：`dev`（vite）、`build`（vite build）
- `vite.config.js`：开发代理 `/api` 和 `/reports` → `http://127.0.0.1:8000`；`@` 别名指 `src`
- `index.html` 标题：AI 测试工作流平台

## 2. 视觉规范（风格 B 浅色简约，必须遵守）
- 页面背景 `#F5F6FA`；卡片白底 `#FFFFFF`；次要面 `#F0F1F6`
- 主色紫 `#4B3FE3`；主色浅 `#EFF0FF`；文字 `#1B1D2A`；次要文字 `#6B7085`；边框 `rgba(27,29,42,.10)`
- 语义色：成功 `#1DC981`、警告 `#EFAA17`、危险 `#E8463A`（仅用于状态徽章）
- 圆角：卡片 12px、控件/标签 8px、胶囊 999px
- 字体：`"PingFang SC","Microsoft YaHei",system-ui`
- **动画要求（核心）**：
  - 工作流看板 = 横排阶段卡片 + 卡片间**细线连接**
  - 已完成段连接线显示**流动虚线**（repeating-linear-gradient + background-position 动画）
  - 当前阶段卡片：紫色边框高亮 + 状态点**脉冲动画**
  - 打回阶段：红色徽章
  - 禁用/跳过阶段：灰色置灰
  - 卡片 hover 上浮 2px + 淡阴影；动画遵循 `@media (prefers-reduced-motion: no-preference)`
- 全局布局：左侧菜单（项目列表 / 连接器设置 / 使用说明占位），右侧内容区，顶栏显示当前页标题

## 3. 后端 API 契约（Base = `/api`，经 vite 代理）

### projects
- `GET /api/projects` → `[{id,name,desc,engine_config,ai_config,created_at}]`
- `POST /api/projects` body `{name,desc,engine_config,ai_config}` → project
- `PUT /api/projects/{id}`、`DELETE /api/projects/{id}`

### workflow
- `GET /api/workflow/stage-library` → `[{type,name,desc,can_skip}]`
- `GET /api/workflow/templates?project_id=` → `[{id,project_id,name,stages,created_at}]`（stages 元素 `{type,name,enabled,source,source_config,ai_config}`）
- `POST /api/workflow/templates` body `{project_id,name,stages:[{type,name,enabled,source,source_config,ai_config}]}`
- `PUT /api/workflow/templates/{id}`、`DELETE /api/workflow/templates/{id}`
- `POST /api/workflow/runs` body `{project_id,template_id,name}` → `{id,project_id,template_id,template_snapshot,status,current_stage_idx,created_at}`
- `GET /api/workflow/runs?project_id=`
- `GET /api/workflow/runs/{run_id}`
- `GET /api/workflow/runs/{run_id}/stages` → `[{id,run_id,stage_type,stage_name,idx,enabled,status,meta}]`
- `PATCH /api/workflow/runs/{run_id}/stages/{stage_id}` body `{status?,meta?}`
- `GET /api/workflow/runs/{run_id}/advance`

### artifacts
- `GET /api/artifacts?run_id=` → `[{id,run_id,stage_type,type,name,file_path,version,source,status,created_at}]`
- `POST /api/artifacts/upload` multipart 字段 `run_id,stage_type,type,name,project,file`
- `GET /api/artifacts/{id}/download`（文件流）
- `DELETE /api/artifacts/{id}`

### connectors
- `GET /api/connectors/kinds` → `[{kind,name,desc}]`
- `GET /api/connectors?project_id=`
- `POST /api/connectors` body `{project_id,kind,name,cfg,enabled}`
- `PUT /api/connectors/{id}`、`DELETE /api/connectors/{id}`
- `POST /api/connectors/fetch` body `{kind,cfg,params}` → `{text,name,files,ref}`
- `GET /api/connectors/mcp/{connector_id}/tools` → `{tools:[{name,description}]}`
- `POST /api/connectors/push` body `{connector_id,payload}`

### ai
- `GET /api/ai/skills`
- `POST /api/ai/summary` body `{run_id}` → `{result:{module,module_cn,business_points,...},attempts,skill,...}`
- `POST /api/ai/generate-cases` body `{run_id,project,evidence}` → `{message,data:{case_set_id,tree,gen_meta}}`
- `POST /api/ai/export` body `{run_id,format:'xmind'|'excel',project}` → `{artifact_id,name,format}`
- `POST /api/ai/review` body `{run_id,result:'approved'|'returned',reason,action,reviewer}`
- `POST /api/ai/regenerate` body `{run_id,project,reason,evidence}`
- `POST /api/ai/import-reviewed` multipart `run_id,project,file` → 回读批准用例集
- `GET /api/ai/case-sets/{run_id}` → `[{id,version,status,content,gen_meta,created_at}]`（content=用例树）

### execution
- `POST /api/exec/env-check?project_id=` → `{ok,items:[{name,ok,detail}]}`
- `POST /api/exec/run` body `{run_id,module,project_id}` → `{execution_id,result:{status,summary,allure_dir,report_dir,error_log}}`
- `GET /api/exec/runs/{run_id}`
- `GET /api/exec/detail/{execution_id}`
- Allure 报告访问：`/reports/{project_name}/{run_id}/allure-report/index.html`（iframe 嵌入）

### 用例树（case tree）结构
```json
{"module":"enterprise","title":"...","version":1,
 "groups":[{"name":"企业-创建","cases":[{"id":"TC-ENT-C01","title":"...","precondition":"","data":"",
   "steps":["..."],"expects":["..."],"priority":"高","api":"POST /x","remark":""}]}]}
```

## 4. 页面与行为

### 4.1 ProjectList（项目列表，首页）
- 卡片网格：每个项目显示名称、描述、流程实例数（可选）、「打开工作台」「模板设计」按钮
- 新建/编辑项目：对话框，字段 name/desc/engine_config（JSON 文本，含 base_url/login_name/password/pytest_project_dir/python/allure_bin/gen_dir）、ai_config（JSON）
- 进入工作台：`/project/{id}`；模板设计：`/project/{id}/designer`
- 删除项目需确认

### 4.2 WorkflowBoard（工作台看板，核心页）
- 顶部：项目名 + 流程实例选择下拉 + 「新建流程实例」（选模板）按钮
- 中部：**动画工作流看板**（AnimatedRail）：
  - 数据 = `/api/workflow/runs/{run_id}/stages`
  - 每阶段一张卡片：序号徽标（已完成=紫底白字，未完成=灰）、阶段名、状态徽章
  - 状态→徽章：pending=待处理(灰)、running=进行中(紫+脉冲点)、success=已完成(绿)、failed=失败(红)、returned=打回(红)、skipped=已跳过(灰)
  - 卡片间连接线：success→success 段显示紫色流动虚线；其余段浅灰实线
  - 底部进度条 = 已完成/总数 + 当前操作提示（取 running 阶段名）
  - 点击卡片 → 右侧抽屉（阶段详情与操作，见 4.2.1）
- 底部：「下一步」按钮调 `/advance`（把当前 running 置 success 并推进下一个），「刷新」按钮
- 也可手动把某阶段置 running（PATCH status=running）

#### 4.2.1 阶段操作抽屉（按 stage_type 区分）
- **requirement（需求）**：上传文件（multipart type=requirement）、粘贴文本（调 connectors/fetch kind=paste 拿 text 后存入需求工件）、填 URL 拉取（kind=url_fetch）、或选连接器；按钮「保存需求工件」；显示已存在需求工件列表（GET artifacts）；「生成需求摘要」（POST ai/summary）→ 展示摘要 JSON
- **api_doc（接口文档）**：上传 yaml/json（type=api_doc）、URL 拉取 OpenAPI、选连接器；「跳过此阶段」（PATCH status=skipped）
- **case_gen（生成用例）**：按钮「生成用例」（POST ai/generate-cases，project=项目名）→ 成功后展示用例树预览（CaseTree 树形）；「重新生成」（POST ai/regenerate）；显示最近用例集（GET ai/case-sets）
- **case_review（用例评审）**：按钮「导出 XMind」「导出 Excel」（POST ai/export）→ 拿到 artifact_id 后调 download 触发下载；「评审通过」（POST ai/review result=approved）；「打回」（弹窗必填原因，POST ai/review result=returned action=regenerate）；「上传修改后的用例」（multipart ai/import-reviewed，xmind/xlsx）→ 回读为批准；显示评审记录
- **auto_gen（自动化生成）**：按钮「生成自动化用例」（需要已有 approved 用例集；POST ai/export 无意义——直接调后端 auto_gen 逻辑，见下）→ 显示 diff 预览（前后差异）与生成结果（new_tc、target 路径）
- **execute（执行报告）**：按钮「环境自检」（POST exec/env-check?project_id=）展示检查项；「执行测试」（POST exec/run，body {run_id, module=用例树module, project_id}）→ 展示 summary（passed/failed/errors/skipped）；「打开 Allure 报告」（新窗口打开 `/reports/{project}/{run_id}/allure-report/index.html`）；失败展示 error_log（预格式化文本）
- 通用：把阶段标记为 failed 可手动触发（PATCH status=failed, meta.error）

> 注：auto_gen 的生成接口在前端对应 `POST /api/ai/auto-generate`，body `{run_id, project_id}`，返回 `{module,target,new_tc,diff_preview,code}`（若后端未提供该端点，前端调用该路径并处理好 404 的兜底提示「后端未实现」——但规格要求后端必须实现，见下）。

### 4.3 FlowDesigner（模板设计/流程画布）
- 左侧「阶段类型库」列表（GET stage-library），每项可拖拽或点击「+」加入画布（**增加卡片**）
- 中间画布：阶段卡片按序横排/纵向列表；支持**拖动排序/组合**（简单实现：上移/下移按钮 或 HTML5 draggable，二选一即可）；卡片工具栏：「启用/禁用开关」（跳过）、「复制」「删除」
- 每张卡片可展开编辑：name、source（下拉：upload/paste/url_fetch/mcp/connector）、source_config（JSON）
- 底部：「保存模板」（POST/PUT /api/workflow/templates，project_id 当前项目）「新建模板」
- 模板列表：可切换/删除

### 4.4 CaseReview（用例评审）
- 也可作为独立页：选中项目+流程实例 → 查看用例集列表（版本/状态/内容树）
- 提供导出、打回、重传、通过（与 4.2.1 case_review 一致，做成可复用组件）

### 4.5 ExecutionReport（执行报告）
- 选中项目+流程实例 → 环境自检项表格；执行历史列表；Allure iframe 嵌入

### 4.6 ConnectorSettings（连接器设置）
- 连接器列表（GET connectors?project_id=0 全局）；新建：选 kind（GET kinds）→ 按 kind 显示配置表单（mcp: command；http: url/headers/json_path；smtp: host/port/user/password；url_fetch: timeout）
- 测试连接：填 params（url 等）调 POST connectors/fetch 展示返回文本
- mcp 连接器：可「列出 tools」（GET mcp/{id}/tools）展示 tools 列表
- 编辑/删除/启用禁用

## 5. 路由
- `/` → ProjectList
- `/project/:id` → WorkflowBoard（含 :runId 可选）
- `/project/:id/designer` → FlowDesigner
- `/project/:id/review` → CaseReview
- `/project/:id/report` → ExecutionReport
- `/connectors` → ConnectorSettings

## 6. 关键组件
- `components/AnimatedRail.vue`：看板横排 + 流动连接线 + 脉冲（核心视觉，务必精致）
- `components/StepCard.vue`：单张阶段卡片
- `components/CaseTree.vue`：用例树（el-tree，节点显示 用例ID 标题 优先级 关联接口）
- `components/CaseTable.vue`：用例表格视图（可选）
- `components/UploadZone.vue`：拖拽上传区
- `components/DiffView.vue`：diff 预览（简单两栏或 pre 文本）
- `components/AllureFrame.vue`：iframe 封装

## 7. 验收
1. `npm run build` 无报错
2. 所有页面可路由渲染；AnimatedRail 动画符合第 2 节规范
3. 关键交互调用正确的 API（字段与第 3 节一致）
