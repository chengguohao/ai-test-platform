# pytest-bdd —— SmartAdmin 测试框架

基于 **pytest + pytest-bdd + Allure** 的接口 / 验收测试框架，当前唯一被测系统为 **SmartAdmin 后台管理系统**。
接口测试（L2）与验收测试（L3）复用同一套「声明式 ApiCase + run_case 引擎」，支持登录 / Token 会话 / 数据清理 / Allure 报告。

## 目录结构

```
tests/
├── conftest.py                        # 全局钩子：节点名 unescape、接口块/断言块日志打印
├── api/
│   └── smartadmin/                    # L2 接口测试（SmartAdmin）
│       ├── conftest.py                #   被测系统 fixture：api_client(登录会话)/ctx/cleanup_registry
│       ├── data/enterprise.yaml       #   业务数据模板
│       └── test_enterprise_crud.py    #   9 条 ApiCase（OA-企业 CRUD + 异常）
└── acceptance/
    └── smartadmin/                    # L3 验收测试（pytest-bdd，可评审 Gherkin）
        ├── conftest.py                #   与 L2 共用同一 fixture 工厂
        ├── features/login.feature     #   登录协议场景
        ├── features/enterprise.feature#   企业 CRUD 场景大纲（Examples 参数化）
        ├── steps/sa_common_steps.py   #   步骤定义（全部委托 run_case，逻辑零重复）
        ├── test_sa_login.py           #   场景运行入口
        └── test_sa_enterprise.py      #   场景运行入口
support/                               # 测试支撑库
├── api_case.py                        # 声明式 ApiCase / 断言 / run_case 引擎 / 信封守卫
├── clients/api_client.py              # HTTP 客户端（cookie jar / envelope / page_query / 自动重登）
└── fixtures/
    ├── context.py                     # ScenarioContext：跨步骤保存 + ${var} 绑定
    └── smartadmin.py                  # 登录 / 清理 / 业务码探测 / fixture 工厂
tools/
├── allure/                            # 本地打包的 Allure CLI（免全局安装）
└── openapi_gen.py                     # OpenAPI → 契约用例生成器（对接 /v3/api-docs）
docs/框架执行流程说明.md                # 新人培训：执行流程 / 引用关系 / 数据流转 / 节点解读
```

## 环境准备

1. SmartAdmin 后端已启动：`SA_BASE_URL` 默认 `http://127.0.0.1:1024`（前端 `http://localhost:8081`）。
2. 复制 `.env.example` 为 `.env`，填入 admin 真实密码：

```
SA_BASE_URL=http://127.0.0.1:1024
SA_LOGIN_NAME=admin
SA_PASSWORD=你的admin密码        # 留空时全部 smartadmin 用例自动 SKIP（不联网、不产生脏数据）
SA_LOGIN_DEVICE=1                # 1=PC
```

3. 安装依赖（已装可跳过）：

```bash
python -m pip install -r requirements/test.txt
```

## 快速开始

```bash
# 只跑 SmartAdmin（L2 接口 + L3 验收）
.\.venv\Scripts\python.exe -m pytest tests/api/smartadmin tests/acceptance/smartadmin -m smartadmin -v --tb=short

# 生成 Allure HTML 报告（无需全局安装 Allure，已内置 tools/allure）
.\.venv\Scripts\python.exe -m pytest tests/api/smartadmin tests/acceptance/smartadmin -m smartadmin -v --tb=short --alluredir allure-results
tools\allure\bin\allure.bat generate allure-results -o allure-report --clean
```

## 这套框架做了什么（对测试经理的价值）

| 能力 | 实现方式 |
|---|---|
| 自动化登录 / Token 会话 | `support/fixtures/smartadmin.py::sa_login()`：dev 环境明文验证码自动解，SM4 加密适配，token 写入会话，后续请求自动携带 |
| 接口执行明细打印（标配） | 根 `tests/conftest.py` 全局钩子：每个 API/BDD/多角色用例自动打印每条接口（名称/方法/地址/状态/耗时/请求/返回/断言），无需脚本自己写；`API_DEBUG=0` 可关 |
| **PyCharm 左侧每条接口一节点（标配）** | **parametrize 展开**：每个 `ApiCase` / `FlowStep` 展开成独立 pytest 节点（PyCharm 原生支持），与 `test_enterprise_crud.py` / `test_role_access_flow.py` 一致 |
| 多角色会话（RBAC） | `.env SA_ROLES_JSON` 配置 admin/reporter/auditor 账号，每角色独立 `ApiClient`+独立 token，`role_registry[role]` 懒登录取会话 |
| 会话过期自动重登 | `ApiClient.set_relogin_hook()`：命中未登录业务码时自动重登 1 次并重发原请求 |
| 统一信封自动断言 | `run_case()` 信封守卫：响应含 `ok` 字段时自动追加 `biz_ok`（ok=true 且 code=0），普通 REST 响应不受影响 |
| 动态业务码（重名/未授权等） | session 级 autouse fixture 故意触发失败场景探测，写入 `SA_CODES`，断言按真实码校验而非写死 |
| 接口间数据串联 | `ScenarioContext`：`save={"…":"ent_id"}` 存值，后续 `${ent_id}` 由 `bind()` 替换 |
| 测试数据清理 | `CleanupRegistry`：注册（删除路径, id），session 结束统一 flush，防数据污染 |
| 可评审 BDD 场景 | `login.feature` / `enterprise.feature`，步骤定义一律委托 `run_case`，与 L2 零重复 |
| Allure 分层报告 | 中文用例名 / feature 分组 / 接口块+断言块步骤树 + HTML 报告 |

## 新增一个业务模块（AI 流水线模式）

按「需求文档 → 手工用例 → AI 生成用例」的闭环，AI 只需产出两类文件，其余全部复用：

```
① L2 层：tests/api/{模块}/test_{module}.py
   - 声明 N 条 ApiCase（方法/路径/入参/断言/save），字段对齐 OpenAPI：http://127.0.0.1:1024/v3/api-docs
   - 文件头加 @pytest.mark.smartadmin；子目录 conftest 复用 make_sa_fixture_functions() 工厂
   - 【强制】必须用 @pytest.mark.parametrize 展开：每个 ApiCase 一条独立 pytest 节点
     （PyCharm 左侧每条接口一节点）。跨角色流程用 FlowStep(role, case) + parametrize 展开，
     禁止写成一个 test 函数 + run_flow/run_flow_as（那样左侧只有 1 个节点）。
     参考：tests/api/smartadmin/test_enterprise_crud.py、test_role_access_flow.py
② L3 层：tests/acceptance/smartadmin/features/{module}.feature + 对应 steps
   - 步骤定义照抄 support 层 run_case 模板
   - 测试入口文件显式 import steps 模块（不要用 pytest_plugins）
③ 本地跑通 → allure generate 出 HTML 报告
```

## 多角色（RBAC）测试

覆盖「不同角色执行同一接口结果不同 / 越权 / 跨角色协同流程」。

1. **预置账号**：SmartAdmin 后台创建 填报员/审核员 账号，`.env` 配置：

   ```
   SA_ROLES_JSON={"admin":{"loginName":"admin","password":"123456"},"reporter":{"loginName":"reporter01","password":"********"},"auditor":{"loginName":"auditor01","password":"********"}}
   ```

2. **独立会话**：每角色走独立登录 → 独立 token → 独立 `ApiClient`；登录日志按角色打印 token。缺账号的角色相关用例自动 SKIP（`requires_role` marker）。

3. **跨角色流程**：
   - L2：`tests/api/smartadmin/test_role_access_flow.py` —— `FlowStep(role, case)` 声明步骤身份，**parametrize 展开成 N 条独立 pytest 节点**（PyCharm 左侧每条接口一节点），`role_registry[role]` 按角色取独立会话执行，`module 级 ctx` 跨步骤串联 `ent_id`。
   - L3：`tests/acceptance/smartadmin/features/role_access_flow.feature` ——「以 {角色} 身份调用…」通用步骤。
   - 越权断言：探测 `SA_CODES["forbidden"]`（低权限角色调用管理操作），断言拒绝业务码。

4. **权限语义说明**：企业模块无真实"审核/打回/报送"接口，演示以「角色权限序列 + 越权拒绝」表达阶段；真实审批流接口接入后仅替换操作步骤。

## 常用命令

| 场景 | 命令 |
|---|---|
| 只看收集（节点数/命名/SKIP 原因） | `.\.venv\Scripts\python.exe -m pytest tests/acceptance/smartadmin --collect-only -q` |
| 只跑 L2 接口 | `.\.venv\Scripts\python.exe -m pytest tests/api/smartadmin -m smartadmin -v --tb=short` |
| 只跑 L3 验收 | `.\.venv\Scripts\python.exe -m pytest tests/acceptance/smartadmin -m smartadmin -v --tb=short` |
| 全量 + Allure | 见「快速开始」 |
| 关闭接口日志（大批量回归） | `$env:API_DEBUG=0` |

> 进阶阅读：执行流程、引用关系、数据流转、节点解读 → [docs/框架执行流程说明.md](docs/框架执行流程说明.md)