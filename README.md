# AiTestPlatform · AI 驱动测试工作流平台

> 从「需求上传 → 接口文档 → 生成用例 → 自动化生成 → 执行报告」整条测试链路由 AI 驱动编排，人只保留不可替代节点：**用例评审按需确认** 与 **执行确认**。
> 不绑定任何第三方平台，每一阶段可自由选择「上传 / 粘贴 / URL / MCP 连接器 / 通用连接器」作为接入源；自动化为**声明式生成**（AI 只产出受 JSON Schema 契约约束的用例声明 → 平台确定性渲染为 pytest 脚本），对齐业界 agent 实践：**MCP 拉实据反幻觉 + Skill 固定流程与输出契约**。

[![CI](https://github.com/chengguohao/ai-test-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/chengguohao/ai-test-platform/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 架构总览

```mermaid
flowchart LR
  U[测试人员] --> W[Web 工作台 · Vue3/Element Plus]
  W -->|5 阶段编排 需求→用例→自动化→执行→报告| A[FastAPI 后端]
  A --> S[Skill 引擎<br/>需求摘要 / 用例生成 / 自动化生成]
  S -->|JSON Schema 契约校验 + 失败重试| M[大模型 API<br/>OpenAI 兼容 · DeepSeek 等]
  A --> C[接入源<br/>上传 / 粘贴 / URL / MCP / HTTP / SMTP]
  A --> P[pytest-bdd 执行<br/>环境自检 → pytest 子进程 → Allure]
  P --> R[(Allure 报告)]
```

## 核心能力

| 能力 | 说明 |
|---|---|
| 5 阶段闭环 | 需求上传 → 接口文档 → 生成用例 → 自动化生成 → 执行报告（看板每阶段自动推进） |
| 流程模板可视化 | 左侧阶段类型库拖入画布，自由排序 / 增删 / 启用禁用（跳过） |
| 接入源自由 | 每阶段可选：上传 / 粘贴 / URL 抓取 / MCP 连接器 / 通用 HTTP / SMTP，可插拔实现 `connectors/base.py` |
| Skill 契约化 | 需求摘要 / 用例生成 / 自动化生成三个 Skill：固定执行流程 + JSON Schema 输出校验，校验不过自动重试 |
| 用例评审闭环 | 导出 XMind / Excel → 打回（必填原因重生成）或人工改后回读 → 通过，不通过不进下一步 |
| 声明式自动化生成 | AI 只输出受 JSON Schema 约束的**用例声明**（不写 Python），平台用确定性模板渲染成 pytest 脚本：断言操作符白名单 / 反例业务码解析 / 资源清理注册 / TC 映射全部由模板保证，杜绝 AI 幻觉发明不支持的语法与断言；落盘前再做语法编译 + op 白名单 + 业务码 key 对齐校验，语法错误拒绝落盘并提示重新生成 |
| 业务码探测对齐 | 会话启动自动探测被测系统真实业务失败码（重名 / 删除不存在 / 越权 / 未登录 / 参数错误），回填 `SA_CODES` 语义组，反例用例按真实 code 断言，探测不到的 key 显式降级提示（不再静默白测） |
| 一键执行 | 上传需求后一键跑完剩余全流程：仅有需求文档 → 执行到生成用例；有接口文档 → 跑通自动化生成与执行测试，失败自动 AI 修复重跑；失败阶段可重置后续跑 |
| 执行总结 | 全流程完成后 AI 生成中文汇报：区分「用例集设计的用例数」与「实际执行的用例数」，附评审 / 打回 / AI 修复 / 多轮执行汇总 |
| 多被测系统适配 | `system_profile` 扫描被测工程画像（marker / 业务码 / 角色体系 / fixture 继承链），动态渲染提示词，换系统只改 gen_dir |
| 执行报告 | 环境自检（区分环境问题）→ pytest 子进程 → Allure 报告 → 失败分级（人工介入 / 打回重生成） |

## 平台界面预览

> 截图保存在 `docs/image/`（仓库内路径）。GitHub 上点击图片文件名即可查看原图。

| 页面 | 截图 |
|---|---|
| 项目列表 | ![项目列表](docs/image/项目列表.png) |
| 需求上传（含 AI 需求摘要） | ![需求上传](docs/image/需求上传.png) |
| 生成用例（业务 / 接口用例树） | ![用例生成](docs/image/用例生成.png) |
| 自动化生成（声明式 → pytest 脚本 + 策略说明） | ![自动化生成](docs/image/自动化生成.png) |
| 执行报告（环境自检 + Allure + AI 总结） | ![执行报告](docs/image/执行报告.png) |
| 知识库（用例沉淀复用） | ![知识库](docs/image/知识库.png) |

## 仓库结构

```
ai-test-platform/
├── backend/                 # FastAPI 后端
│   └── app/
│       ├── api/             # projects / workflow / artifacts / connectors / ai / exec
│       ├── connectors/      # 可插拔接入源（本地/粘贴/URL/MCP/HTTP/SMTP）
│       └── services/
│           ├── skills/      # Skill 包（固定规则 + 输出契约）
│           └── skill_engine.py · ai_llm.py · case_gen.py · auto_gen.py · executor.py
├── frontend/                # Vue3 + Vite + Element Plus（动画工作流看板）
├── pytest-bdd/              # pytest-bdd 测试框架库（被测系统示例：SmartAdmin）
│   ├── support/             # ApiCase / 运行时断言 / 角色客户端 / 上下文
│   ├── tests/api|acceptance # 生成的接口用例 + BDD 行为用例
│   └── tools/allure/        # Allure 命令行（执行用）
├── docs/                    # 操作手册 + 需求/接口模板 + 可复现示例（请假/通知公告）
├── .github/workflows/ci.yml # CI 冒烟
├── .env.example             # 环境变量模板
├── LICENSE                  # MIT
└── start.bat / start.ps1    # 一键启动（后端 8000 + 前端 5173）
```

## 快速开始

前置：Node ≥ 18、Python ≥ 3.10。

### 1. 启动平台

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
copy .env.example .env        # 填写 LLM_API_KEY（OpenAI 兼容任意模型）
.\start.bat                   # 一键启动后端 + 前端
```

打开 http://localhost:5173 → 新建项目（填被测系统 base_url / pytest 项目路径 / LLM Key）→ 设计流程模板 → 新建流程实例 → 按看板逐步操作。

### 2. 全流程跑通示例（推荐）

本仓库内置 **SmartAdmin** 作为可复现被测系统示例（含请假 / 通知公告的需求与接口文档、生成的 pytest 用例与角色权限 BDD 用例）：

- **SmartAdmin**：由 1024 创新实验室开源的 SpringBoot + Vue 中后台系统（MIT 协议）—— [https://github.com/1024-lab/smart-admin](https://github.com/1024-lab/smart-admin)
- 完整闭环需要先部署 SmartAdmin 后端，并在 `pytest-bdd/.env` 配置被测账号（见 `pytest-bdd/.env.example`）；未配置时相关用例**自动 SKIP**，不影响平台其余环节体验。

### 3. 接入你自己的被测系统

在项目 `engine_config` 填：`base_url`、`login_name`、`password`、`pytest_project_dir`、`python`、`allure_bin`、`gen_dir`。新系统按 `docs/被测系统接入与平台操作手册.md` 适配（登记业务 marker、生成业务码模块、确认 fixtures 继承链），平台提示词会按画像自动适配。


## 数据库与初始化

- 默认 SQLite：数据库文件在本地 `data/app.db`，**首次启动后端自动建表**并补齐迁移列；运行期数据（项目/流程/用例/执行记录）**不入 Git 仓库**（`.gitignore` 的 `data/`），clone 后无需任何数据库准备；
- 新建项目时自动生成「默认流程」模板（需求上传 → 接口文档 → 生成用例 → 自动化生成 → 执行报告，5 阶段，可在流程设计页修改）；
- 生产可切 MySQL：`.env` 设置 `DATABASE_URL=mysql+pymysql://user:pass@host:3306/ai_test_platform`；
- 仓库内置示例需求与接口文档（`docs/templates/examples`：员工请假、通知公告、企业管理），新建项目后可直接上传体验「生成用例 → 评审 → 自动化生成」全流程。
## 测试执行

环境自检 → `pytest tests/api/{module} -m smartadmin --alluredir …` → `allure generate` → 页面 iframe 打开 `/reports/{project}/{run_id}/allure-report/index.html`。

## 已知限制

- 平台自身目前仅 import / build 冒烟测试（CI），业务链路以人工验收为准；
- SmartAdmin 全链路用例依赖外部被测系统，CI 中自动 SKIP；
- AI 调用暂无自动预算 / 成本统计（见路线图）；
- `SECRET_KEY` 默认值仅供本地开发，生产请务必在 `.env` 覆盖。

## 路线图

- AI 调用成本统计与预算控制
- 平台单元测试与 CI 增强（新增用例生成 / 状态机回归）
- GitHub Pages 在线演示站

## License

[MIT](LICENSE)