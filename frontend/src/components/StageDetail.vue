<template>
  <transition name="panel-fade">
    <div v-if="modelValue" class="stage-panel">
      <div class="panel-header">
        <span class="panel-title">阶段详情 · {{ stage?.stage_name || '' }}</span>
        <el-button size="small" text @click="emit('update:modelValue', false)">
          <el-icon><Close /></el-icon>收起
        </el-button>
      </div>
      <div v-if="stage" v-loading="loading" class="stage-detail">
      <!-- 阶段通用信息 -->
      <div class="stage-meta">
        <span class="pill" :class="pillType">{{ stage.stage_type }}</span>
        <span class="status-badge" :class="stage.status">{{ statusText }}</span>
        <span v-if="stage.meta?.error" class="meta-error">错误：{{ stage.meta.error }}</span>
      </div>

      <!-- 本步骤操作指引：告诉用户这一步做什么、做完点哪里 -->
      <el-alert
        v-if="stageGuide"
        type="info"
        :closable="false"
        class="mb8"
        :title="`本步骤怎么做：${stageGuide}`"
      />

      <!-- ============ requirement：需求上传 ============ -->
      <template v-if="stage.stage_type === 'requirement'">
        <div class="block-title">需求来源</div>
        <el-tabs v-model="reqTab" class="req-tabs">
          <el-tab-pane label="上传文件" name="upload">
            <UploadZone
              accept=".md,.txt,.doc,.docx,.pdf,.xlsx"
              accept-hint="支持 md / txt / doc / pdf / xlsx"
              placeholder="点击或拖拽需求文档到此处"
              @change="reqFile = $event"
            />
          </el-tab-pane>
          <el-tab-pane label="粘贴文本" name="paste">
            <el-input
              v-model="pasteText"
              type="textarea"
              :rows="5"
              placeholder="粘贴需求文本…"
            />
            <div class="row-actions">
              <el-button size="small" :loading="pasting" @click="fetchPaste">拉取</el-button>
            </div>
          </el-tab-pane>
          <el-tab-pane label="URL 拉取" name="url">
            <el-input v-model="reqUrl" placeholder="https://... 需求页 / Swagger" />
            <div class="row-actions">
              <el-button size="small" :loading="urlLoading" @click="fetchUrl">拉取</el-button>
            </div>
          </el-tab-pane>
          <el-tab-pane label="连接器" name="connector">
            <el-select v-model="selConnectorId" placeholder="选择连接器" style="width: 100%">
              <el-option
                v-for="c in connectors"
                :key="c.id"
                :label="`${c.name}（${c.kind}）`"
                :value="c.id"
              />
            </el-select>
            <template v-if="selConnector">
              <template v-if="selConnector.kind === 'mcp'">
                <el-button size="small" class="mt8" @click="loadMcpTools">列出 MCP tools</el-button>
                <el-select v-if="mcpTools.length" v-model="mcpTool" class="mt8" style="width: 100%">
                  <el-option v-for="t in mcpTools" :key="t.name" :label="t.name" :value="t.name" />
                </el-select>
              </template>
              <div class="row-actions">
                <el-button size="small" :loading="connLoading" @click="fetchConnector">拉取</el-button>
              </div>
            </template>
          </el-tab-pane>
        </el-tabs>

        <div v-if="fetched" class="fetched-box">
          <div class="fetched-head">
            <b>{{ fetched.name }}</b>
            <span class="muted">{{ (fetched.text || '').length }} 字符</span>
          </div>
          <pre class="code-block fetched-preview">{{ fetched.text }}</pre>
        </div>

        <el-form-item label="含图片？" class="mt8">
          <el-switch
            v-model="reqHasImages"
            active-text="是"
            inactive-text="否"
          />
          <div class="form-hint">
            需求文档是否包含图片/截图/流程图/原型图？选「是」会用副模型（多模态）识别 docx 内嵌图并自动规范化。
          </div>
        </el-form-item>

        <el-button type="primary" class="mt8" :loading="saving" @click="saveRequirement">
          <el-icon style="margin-right: 4px"><Upload /></el-icon>保存需求工件
        </el-button>
        <el-button class="mt8" :loading="summarizing" :disabled="saving || !requirementArtifacts.length" @click="genSummary">
          <el-icon style="margin-right: 4px"><MagicStick /></el-icon>生成需求摘要
        </el-button>
        <div class="form-hint" v-if="saving" style="color: #e6a23c">需求工件保存中，请稍候…（完成后才能生成摘要）</div>

        <div v-if="reqHasImages" class="mt8">
          <div class="block-title">图片识别与规范化</div>
          <div class="think-collapse mt8">
            <el-collapse v-model="thinkOpenReq">
              <el-collapse-item name="reqVision">
                <template #title>
                  <span class="think-title">识图规范化进度（{{ reqThinkSteps.length }} 步，点击折叠/展开）</span>
                </template>
                <div class="think-list">
                  <div v-if="!reqThinkSteps.length" class="think-line muted">等待后台启动识图规范化…</div>
                  <div v-for="(s, i) in reqThinkSteps" :key="i" class="think-line">
                    <span class="think-ts">{{ s.ts }}</span>
                    <span class="think-text">{{ s.text }}</span>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>

        <div v-if="summary" class="mt8">
          <div class="block-title">
            需求摘要
            <span class="muted" v-if="genModel" style="margin-left: 8px">使用 AI 模型：{{ genModel }}</span>
          </div>
          <pre class="code-block">{{ formatJson(summary) }}</pre>
          <el-alert
            type="success"
            :closable="false"
            class="mt8"
            title="摘要已保存，关闭本页面后不会丢失。确认无误后即可进入下一步，状态由步骤自动控制。"
          />
        </div>

        <div class="mt8">
          <div class="block-title">已有需求工件</div>
          <ArtifactList :items="requirementArtifacts" @download="downloadArtifact" @remove="removeArtifact" />
        </div>
      </template>

      <!-- ============ api_doc：接口文档 ============ -->
      <template v-else-if="stage.stage_type === 'api_doc'">
        <div class="block-title">接口文档来源</div>
        <el-tabs v-model="apiTab">
          <el-tab-pane label="上传 yaml/json" name="upload">
            <UploadZone
              accept=".yaml,.yml,.json,.txt,.md"
              placeholder="点击或拖拽 OpenAPI / 接口文档到此处"
              @change="apiFile = $event"
            />
          </el-tab-pane>
          <el-tab-pane label="URL 拉取 OpenAPI" name="url">
            <el-input v-model="apiUrl" placeholder="https://.../swagger.json / openapi.yaml" />
            <div class="row-actions">
              <el-button size="small" :loading="apiUrlLoading" @click="fetchApiUrl">拉取</el-button>
            </div>
          </el-tab-pane>
          <el-tab-pane label="连接器" name="connector">
            <el-select v-model="apiConnectorId" placeholder="选择连接器" style="width: 100%">
              <el-option
                v-for="c in connectors"
                :key="c.id"
                :label="`${c.name}（${c.kind}）`"
                :value="c.id"
              />
            </el-select>
            <div class="row-actions">
              <el-button size="small" :loading="apiConnLoading" @click="fetchApiConnector">拉取</el-button>
            </div>
          </el-tab-pane>
        </el-tabs>

        <div v-if="apiFetched" class="fetched-box">
          <div class="fetched-head">
            <b>{{ apiFetched.name }}</b>
            <span class="muted">{{ (apiFetched.text || '').length }} 字符</span>
          </div>
          <pre class="code-block fetched-preview">{{ apiFetched.text }}</pre>
        </div>

        <el-button type="primary" class="mt8" :loading="savingApi" @click="saveApiDoc">
          <el-icon style="margin-right: 4px"><Upload /></el-icon>保存接口文档工件
        </el-button>
        <el-button class="mt8" @click="skipStage">跳过此阶段</el-button>

        <div class="mt8">
          <div class="block-title">已有接口工件</div>
          <ArtifactList :items="apiArtifacts" @download="downloadArtifact" @remove="removeArtifact" />
        </div>
      </template>

      <!-- ============ case_gen：生成用例 ============ -->
      <template v-else-if="stage.stage_type === 'case_gen'">
        <div class="row-actions">
          <el-radio-group v-model="caseType" style="margin-right: 12px">
            <el-radio-button label="business">业务功能用例</el-radio-button>
            <!-- 仅当已上传接口文档时才允许选「接口测试用例」：
                 仅需求文档场景强制走业务用例，避免生成引用 api_client 等不存在的 fixture 的 API 用例脚本。 -->
            <el-radio-button label="api" :disabled="!hasApiDoc">接口测试用例</el-radio-button>
          </el-radio-group>
          <el-button type="primary" :loading="generating" @click="generateCases">
            <el-icon style="margin-right: 4px"><MagicStick /></el-icon>生成用例
          </el-button>
          <el-button :loading="regenerating" @click="regenerate">重新生成</el-button>
          <el-button :loading="exporting === 'xmind'" @click="exportCases('xmind')">
            <el-icon style="margin-right: 4px"><Download /></el-icon>导出 XMind
          </el-button>
          <el-button :loading="exporting === 'excel'" @click="exportCases('excel')">
            <el-icon style="margin-right: 4px"><Download /></el-icon>导出 Excel
          </el-button>
          <el-button
            type="success"
            plain
            :loading="reviewing"
            :disabled="!typedCaseSets.length || currentReviewed"
            @click="approveCases"
          >
            <el-icon style="margin-right: 4px"><CircleCheck /></el-icon>{{ currentReviewed ? '已评审通过' : '评审通过' }}
          </el-button>
        </div>
        <div v-if="!hasApiDoc" class="form-hint mt8" style="color: #e6a23c">
          当前未上传接口文档，仅支持生成「业务功能用例」；如需接口测试用例，请先到「接口文档」阶段上传接口文档。
        </div>
        <div class="form-hint mt8" v-if="caseType==='business'">
          业务功能用例：站在用户操作视角，步骤描述页面/业务流程操作，预期写业务可见结果，供手工测试执行。
        </div>
        <div class="form-hint mt8" v-else>
          接口测试用例：每条对应一个具体接口，步骤写请求构造，预期写响应/业务码校验，供自动化直接转换。
        </div>
        <el-alert
          v-if="stage.status==='returned' || stage.meta?.return_reason"
          :title="`该阶段已被打回，原因：${stage.meta?.return_reason || '未填写'}。请按原因重新生成。`"
          type="warning"
          :closable="false"
          class="mt8"
        />
        <el-alert
          v-if="generateMsg"
          :title="generateMsg"
          type="success"
          :closable="false"
          class="mt8"
        />

        <!-- 生成进度条 + 思考过程：LLM 生成耗时较长（通常 30~120 秒），给用户可视反馈 -->
        <div v-if="generating || regenerating" class="gen-progress mt8">
          <el-progress
            :percentage="genProgress"
            :indeterminate="genProgress >= 95"
            :stroke-width="10"
            status="success"
          />
          <div class="form-hint">AI 正在生成{{ caseType === 'api' ? '接口测试用例' : '业务功能用例' }}，通常需要 30~120 秒，请勿关闭抽屉…</div>
          <div class="think-collapse mt8">
            <el-collapse v-model="thinkOpen">
              <el-collapse-item name="think">
                <template #title>
                  <span class="think-title">思考过程（{{ thinkSteps.length }} 步，点击折叠/展开）</span>
                </template>
                <div class="think-list">
                  <div v-if="!thinkSteps.length" class="think-line muted">等待 AI 返回过程信息…</div>
                  <div v-for="(s, i) in thinkSteps" :key="i" class="think-line">
                    <span class="think-ts">{{ s.ts }}</span>
                    <span class="think-text">{{ s.text }}</span>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>

        <div v-if="latestTree" class="mt8">
          <div class="block-title">
            最新用例树预览
            <el-tag size="small" :type="latestTree.case_type === 'api' ? 'warning' : 'success'" effect="plain" style="margin-left: 8px">
              {{ latestTree.case_type === 'api' ? '接口测试用例' : '业务功能用例' }}
            </el-tag>
            <span class="muted" v-if="caseGenModel" style="margin-left: 8px">使用 AI 模型：{{ caseGenModel }}</span>
          </div>
          <CaseTree :tree="latestTree" />
          <el-button size="small" class="mt8" @click="showTreeTable = !showTreeTable">
            {{ showTreeTable ? '收起表格' : '切换表格视图' }}
          </el-button>
          <CaseTable v-if="showTreeTable" :tree="latestTree" class="mt8" />
        </div>

        <div class="mt8">
          <div class="block-title">用例集列表（{{ caseType === 'api' ? '接口测试用例' : '业务功能用例' }}）</div>
          <el-empty v-if="!typedCaseSets.length" :description="尚无该类型的用例集" :image-size="40" />
          <div v-for="cs in typedCaseSets" :key="cs.id" class="case-set-item" @click="previewCaseSet(cs)">
            <div>
              <b>v{{ cs.version }}</b>
              <span class="status-badge" :class="cs.status" style="margin-left: 8px">{{ csStatus(cs.status) }}</span>
            </div>
            <span class="muted">{{ formatDate(cs.created_at) }}</span>
          </div>
        </div>

        <div class="mt8">
          <div class="block-title">生成文件与日志</div>
          <ArtifactList :items="caseGenArtifacts" @download="downloadArtifact" @remove="removeArtifact" />
        </div>
      </template>

      <!-- ============ skill：AI 处理（独立 Skill 卡片） ============ -->
      <template v-else-if="stage.stage_type === 'skill'">
        <el-alert type="info" :closable="false" title="独立 AI 处理卡片：选一种 AI 能力运行，结果存为工件，可插到任意步骤" class="mb8" />
        <el-alert
          v-if="boundSkillId"
          type="success"
          :closable="false"
          class="mb8"
        >
          <template #title>
            本步骤已绑定 Skill：<b>{{ boundSkillName }}</b>
            <span class="muted">（模板设计中预选；可在此更换，更换后自动保存）</span>
          </template>
        </el-alert>
        <div class="block-title">选择 AI 能力</div>
        <el-select v-model="selSkillId" style="width:100%" placeholder="选择 Skill" @change="persistSkillBind">
          <el-option v-for="s in skills" :key="s.id" :label="`${s.name}（${s.id}）`" :value="s.id" />
        </el-select>
        <div class="block-title">运行参数（JSON，可空）</div>
        <el-input v-model="skillInputsText" type="textarea" :rows="4" placeholder='{"requirement": "..."}' />
        <div class="row-actions">
          <el-button type="primary" :loading="skillRunning" @click="runSkill">运行 Skill</el-button>
        </div>
        <div v-if="skillResult" class="mt8">
          <div class="block-title">运行结果</div>
          <pre class="code-block">{{ skillResult.text }}</pre>
        </div>
        <div class="mt8">
          <div class="block-title">Skill 结果工件</div>
          <ArtifactList :items="skillArtifacts" @download="downloadArtifact" @remove="removeArtifact" />
        </div>
      </template>

      <!-- ============ mcp：平台取数（独立 MCP 卡片） ============ -->
      <template v-else-if="stage.stage_type === 'mcp'">
        <el-alert type="info" :closable="false" title="独立取数卡片：从已注册的公司平台(MCP)拉一份真实资料存为工件，可插到任意步骤" class="mb8" />
        <div class="block-title">选择 MCP 连接器</div>
        <el-select v-model="mcpConnectorId" style="width:100%" placeholder="选择 MCP Server">
          <el-option v-for="c in mcpConnectors" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <template v-if="selMcpConnector">
          <el-button size="small" class="mt8" :loading="mcpLoadingTools" @click="loadMcpTools2">列出 tools</el-button>
          <el-select v-if="mcpTools2.length" v-model="mcpTool2" class="mt8" style="width:100%" placeholder="选择 tool">
            <el-option v-for="t in mcpTools2" :key="t.name" :label="t.name" :value="t.name" />
          </el-select>
          <div class="block-title">tool 参数（JSON，可空）</div>
          <el-input v-model="mcpArgsText" type="textarea" :rows="3" placeholder="{}" />
          <div class="row-actions">
            <el-button type="primary" :loading="mcpFetching" @click="runMcpFetch">拉取并保存为工件</el-button>
          </div>
        </template>
        <div v-if="mcpFetchResult" class="mt8">
          <div class="block-title">拉取结果</div>
          <pre class="code-block">{{ mcpFetchResult }}</pre>
        </div>
        <div class="mt8">
          <div class="block-title">取数工件</div>
          <ArtifactList :items="mcpArtifacts" @download="downloadArtifact" @remove="removeArtifact" />
        </div>
      </template>

      <!-- ============ case_review：用例评审（复用 ReviewPanel） ============ -->
      <template v-else-if="stage.stage_type === 'case_review'">
        <ReviewPanel :project="project" :run="run" @changed="onReviewChanged" />
      </template>

      <!-- ============ auto_gen：自动化生成 ============ -->
      <template v-else-if="stage.stage_type === 'auto_gen'">
        <el-alert
          type="info"
          :closable="false"
          title="基于已批准用例集 + 接口文档，生成 pytest 增量自动化用例"
          class="mb8"
        />
        <el-alert
          v-if="stage.meta?.fix_rounds"
          type="warning"
          :closable="false"
          class="mb8"
          :title="`本实例已经历 ${stage.meta.fix_rounds} 轮 AI 自动修复${stage.meta.fix_analysis ? '，最近结论：' + (stage.meta.fix_analysis.overall_conclusion || '') : ''}`"
        />
        <el-button type="primary" :loading="autoGenerating" @click="autoGenerate">
          <el-icon style="margin-right: 4px"><MagicStick /></el-icon>生成自动化用例
        </el-button>
        <el-alert
          v-if="stage.meta?.auto_result || autoResult"
          type="warning"
          :closable="false"
          class="mt8"
          title="再次点击「生成自动化用例」将基于最新需求与接口文档全量重新生成并覆盖旧脚本"
        />

        <!-- 生成进度条 + 思考过程：LLM 生成耗时较长，给用户可视反馈 -->
        <div v-if="autoGenerating" class="gen-progress mt8">
          <el-progress
            :percentage="genProgress"
            :indeterminate="genProgress >= 95"
            :stroke-width="10"
            status="success"
          />
          <div class="form-hint">AI 正在生成自动化脚本（含校验重试，最多 3 轮），通常需要 1~3 分钟，请勿关闭抽屉…</div>
          <div class="think-collapse mt8">
            <el-collapse v-model="thinkOpen">
              <el-collapse-item name="think">
                <template #title>
                  <span class="think-title">思考过程（{{ thinkSteps.length }} 步，点击折叠/展开）</span>
                </template>
                <div class="think-list">
                  <div v-if="!thinkSteps.length" class="think-line muted">等待 AI 返回过程信息…</div>
                  <div v-for="(s, i) in thinkSteps" :key="i" class="think-line">
                    <span class="think-ts">{{ s.ts }}</span>
                    <span class="think-text">{{ s.text }}</span>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>

        <div v-if="autoResult" class="mt8">
          <div class="block-title">生成结果</div>
          <div class="result-grid">
            <div class="result-item"><label>模块</label><span>{{ autoResult.module }}</span></div>
            <div class="result-item"><label>目标文件</label><span class="path">{{ autoResult.target }}</span></div>
            <div class="result-item"><label>模式</label><span>{{ autoResult.regenerated ? '全量覆盖旧脚本' : '新建' }}</span></div>
            <div class="result-item"><label>AI 模型</label><span>{{ autoResult.model || '-' }}</span></div>
            <div class="result-item"><label>生成 TC</label>
              <span class="tc-chips">
                <el-tag v-for="tc in autoResult.new_tc || []" :key="tc" size="small" effect="plain">{{ tc }}</el-tag>
                <span v-if="!(autoResult.new_tc || []).length" class="muted">-</span>
              </span>
            </div>
          </div>
          <div v-if="autoResult.desc" class="block-title mt8">生成策略说明（请测试人员核对）</div>
          <p v-if="autoResult.desc" class="form-hint" style="line-height:1.7; white-space: pre-wrap">{{ autoResult.desc }}</p>
          <div class="block-title mt8">Diff 预览</div>
          <DiffView :diff="autoResult.diff_preview" />
          <div class="block-title mt8">生成代码</div>
          <pre class="code-block">{{ autoResult.code }}</pre>
        </div>

        <div class="mt8">
          <div class="block-title">生成文件与日志</div>
          <ArtifactList :items="autoGenArtifacts" @download="downloadArtifact" @remove="removeArtifact" />
        </div>
      </template>

      <!-- ============ execute：执行报告 ============ -->
      <template v-else-if="stage.stage_type === 'execute'">
        <div class="row-actions">
          <el-button :loading="envChecking" @click="envCheck">
            <el-icon style="margin-right: 4px"><Monitor /></el-icon>环境自检
          </el-button>
          <el-button type="primary" :loading="executing" @click="execRun">
            <el-icon style="margin-right: 4px"><VideoPlay /></el-icon>执行测试
          </el-button>
          <el-button :disabled="!allureUrl" @click="openAllure">
            <el-icon style="margin-right: 4px"><Link /></el-icon>打开 Allure 报告
          </el-button>
        </div>

        <div v-if="envItems.length" class="mt8">
          <div class="block-title">环境自检结果</div>
          <el-table :data="envItems" size="small" border>
            <el-table-column prop="name" label="检查项" min-width="150" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <span class="pill" :class="row.ok ? 'pill-success' : 'pill-danger'">
                  {{ row.ok ? '通过' : '失败' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
          </el-table>
        </div>

        <!-- 执行进度条 + 思考过程（pytest 后台执行时） -->
        <div v-if="executing" class="gen-progress mt8">
          <el-progress
            :percentage="genProgress"
            :indeterminate="genProgress >= 95"
            :stroke-width="10"
            status="success"
          />
          <div class="form-hint">pytest 正在执行并生成 Allure 报告，请勿关闭抽屉…</div>
          <div class="think-collapse mt8">
            <el-collapse v-model="thinkOpen">
              <el-collapse-item name="think">
                <template #title>
                  <span class="think-title">执行过程（{{ thinkSteps.length }} 步，点击折叠/展开）</span>
                </template>
                <div class="think-list">
                  <div v-if="!thinkSteps.length" class="think-line muted">等待执行过程信息…</div>
                  <div v-for="(s, i) in thinkSteps" :key="i" class="think-line">
                    <span class="think-ts">{{ s.ts }}</span>
                    <span class="think-text">{{ s.text }}</span>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>

        <div v-if="execResult" class="mt8">
          <div class="block-title">执行结果</div>
          <div class="summary-stats">
            <div class="stat"><b>{{ execResult.summary?.total ?? 0 }}</b><span>总计</span></div>
            <div class="stat ok"><b>{{ execResult.summary?.passed ?? 0 }}</b><span>通过</span></div>
            <div class="stat fail"><b>{{ (execResult.summary?.failures ?? 0) + (execResult.summary?.errors ?? 0) }}</b><span>失败/错误</span></div>
            <div class="stat skip"><b>{{ execResult.summary?.skipped ?? 0 }}</b><span>跳过</span></div>
          </div>
          <el-alert
            v-if="execResult.status"
            class="mt8"
            :type="execResult.status === 'passed' ? 'success' : 'error'"
            :closable="false"
            :title="execResult.status === 'passed' ? '执行通过' : '执行失败'"
          />
          <div v-if="execCases.length" class="block-title mt8">逐用例结果（{{ execCases.length }} 条）</div>
          <el-table v-if="execCases.length" :data="execCases" size="small" class="mt8" max-height="320">
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status==='通过'?'success':(row.status==='跳过'?'info':'danger')" effect="dark">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="name" label="用例名" min-width="280" show-overflow-tooltip />
            <el-table-column label="耗时" width="90">
              <template #default="{ row }">{{ row.time ? (row.time*1000).toFixed(0)+' ms' : '-' }}</template>
            </el-table-column>
          </el-table>
          <div v-if="execResult.error_log" class="block-title mt8">错误日志</div>
          <pre v-if="execResult.error_log" class="code-block">{{ execResult.error_log }}</pre>
        </div>

        <!-- 执行失败 → AI 检查修复闭环 -->
        <div v-if="execResult && execResult.status === 'failed'" class="fix-box mt8">
          <div class="block-title">AI 检查修复</div>
          <el-alert
            type="warning"
            :closable="false"
            title="本次执行未通过。可让 AI 分析失败根因：若判定为脚本问题，会自动打回并重新生成自动化脚本；完成后请再手工点击「执行测试」复验。"
          />
          <el-button type="primary" class="mt8" :loading="fixing" @click="runAutoFix">
            <el-icon style="margin-right: 4px"><MagicStick /></el-icon>AI 检查修复并重新生成
          </el-button>

          <!-- 修复过程进度条 + 思考过程 -->
          <div v-if="fixing" class="gen-progress mt8">
            <el-progress
              :percentage="genProgress"
              :indeterminate="genProgress >= 95"
              :stroke-width="10"
              status="success"
            />
            <div class="form-hint">AI 正在分析失败根因并重新生成脚本（分析 + 生成约需 1~3 分钟），请勿关闭抽屉…</div>
            <div class="think-collapse mt8">
              <el-collapse v-model="thinkOpen">
                <el-collapse-item name="think">
                  <template #title>
                    <span class="think-title">思考过程（{{ thinkSteps.length }} 步，点击折叠/展开）</span>
                  </template>
                  <div class="think-list">
                    <div v-if="!thinkSteps.length" class="think-line muted">等待 AI 返回过程信息…</div>
                    <div v-for="(s, i) in thinkSteps" :key="i" class="think-line">
                      <span class="think-ts">{{ s.ts }}</span>
                      <span class="think-text">{{ s.text }}</span>
                    </div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>
          </div>

          <!-- 修复结果：AI 分析结论 -->
          <div v-if="fixResult" class="mt8">
            <el-alert :type="fixResult.regenerated ? 'success' : 'info'" :closable="false"
                      :title="fixResult.message" />
            <div v-if="fixResult.analysis" class="fix-analysis mt8">
              <div class="block-title">AI 根因分析（第 {{ fixResult.fix_round }} 轮）</div>
              <p class="form-hint">{{ fixResult.analysis.overall_conclusion }}</p>
              <el-table v-if="(fixResult.analysis.root_causes || []).length"
                        :data="fixResult.analysis.root_causes" size="small" border>
                <el-table-column prop="case" label="失败用例" min-width="180" show-overflow-tooltip />
                <el-table-column prop="cause" label="根因" min-width="220" show-overflow-tooltip />
                <el-table-column label="性质" width="100">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.is_script_bug ? 'danger' : 'warning'" effect="plain">
                      {{ row.is_script_bug ? '脚本问题' : '疑似系统缺陷' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
              <div v-if="fixResult.analysis.regen_instructions" class="mt8">
                <div class="block-title">重生成修改指令</div>
                <pre class="code-block">{{ fixResult.analysis.regen_instructions }}</pre>
              </div>
            </div>
          </div>
        </div>

        <div class="mt8">
          <div class="block-title">执行文件与日志</div>
          <ArtifactList :items="executeArtifacts" @download="downloadArtifact" @remove="removeArtifact" />
        </div>
      </template>

      <!-- ============ 未知阶段 ============ -->
      <template v-else>
        <el-empty description="该阶段类型暂未实现具体操作" :image-size="60" />
      </template>

      <!-- 通用操作：状态由步骤自动控制，仅保留关闭按钮 -->
      <div class="drawer-footer">
        <el-button size="small" @click="emit('update:modelValue', false)">关闭</el-button>
      </div>
    </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import UploadZone from './UploadZone.vue'
import CaseTree from './CaseTree.vue'
import CaseTable from './CaseTable.vue'
import DiffView from './DiffView.vue'
import ArtifactList from './ArtifactList.vue'
import ReviewPanel from './ReviewPanel.vue'
import {
  artifactApi,
  connectorApi,
  aiApi,
  execApi,
  workflowApi,
  allureReportUrl
} from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  project: { type: Object, default: null },
  run: { type: Object, default: null },
  stage: { type: Object, default: null }
})

const emit = defineEmits(['update:modelValue', 'changed'])

/* ---------- 通用 ---------- */
const loading = ref(false)
const artifacts = ref([])
const connectors = ref([])

/* 各阶段操作指引：让用户一眼知道这一步做什么、做完点哪里（状态由步骤自动控制） */
const STAGE_GUIDE = {
  requirement: '选择需求来源（上传文件 / 粘贴文本 / URL / 连接器）→ 点「保存需求工件」→ 点「生成需求摘要」，完成后本阶段自动标记为已完成。',
  api_doc: '上传或拉取接口文档（OpenAPI / Swagger）→ 点「保存接口文档工件」，完成后自动标记为已完成。暂无接口文档可点「跳过此阶段」。',
  case_gen: '选择用例类型（业务功能 / 接口测试）→ 点「生成用例」，AI 自动产出用例树；可「导出 XMind/Excel」；检查无误后按类型点「评审通过」，全部评完自动进入下一步。',
  case_review: '评审最新用例集：满意点「评审通过」；不满意填写原因「打回」，流程会自动回到生成用例阶段重新生成。',
  auto_gen: '点「生成自动化用例」：基于已批准用例 + 接口文档生成 pytest 脚本，完成后本阶段自动标记为已完成。',
  execute: '先「环境自检」确认环境可用 → 点「执行测试」→ 查看结果与 Allure 报告，执行通过后本阶段自动标记为已完成。',
  skill: '选择一种 AI 能力 → 可填运行参数 → 点「运行 Skill」，结果自动存为工件。',
  mcp: '选择 MCP 连接器 → 「列出 tools」并选择 → 点「拉取并保存为工件」。'
}
const stageGuide = computed(() => STAGE_GUIDE[props.stage?.stage_type] || '')

const statusText = computed(() => {
  const map = { pending: '待处理', running: '进行中', success: '已完成', failed: '失败', returned: '打回', pending_review: '待评审', skipped: '已跳过' }
  return map[props.stage?.status] || props.stage?.status || ''
})
const pillType = computed(() => {
  const map = {
    requirement: 'pill-primary',
    api_doc: 'pill',
    case_gen: 'pill-primary',
    case_review: 'pill',
    auto_gen: 'pill-primary',
    skill: 'pill-primary',
    mcp: 'pill',
    execute: 'pill-success'
  }
  return map[props.stage?.stage_type] || 'pill'
})

const requirementArtifacts = computed(() =>
  artifacts.value.filter((a) => a.stage_type === 'requirement')
)
const apiArtifacts = computed(() => artifacts.value.filter((a) => a.stage_type === 'api_doc'))
const skillArtifacts = computed(() => artifacts.value.filter((a) => a.stage_type === 'skill'))
const mcpArtifacts = computed(() => artifacts.value.filter((a) => a.stage_type === 'mcp'))
/* 生成文件 + 生成日志（gen_log / case_tree / auto_file / exec_log 等） */
const caseGenArtifacts = computed(() => artifacts.value.filter((a) => a.stage_type === 'case_gen'))
const autoGenArtifacts = computed(() => artifacts.value.filter((a) => a.stage_type === 'auto_gen'))
const executeArtifacts = computed(() => artifacts.value.filter((a) => a.stage_type === 'execute'))

function makeTextFile(text, filename) {
  return new File([text || ''], filename, { type: 'text/plain' })
}

async function uploadArtifact(file, type, name, hasImages = false) {
  const fd = new FormData()
  fd.append('run_id', props.run.id)
  fd.append('stage_type', props.stage.stage_type)
  fd.append('type', type)
  fd.append('name', name || file.name)
  fd.append('project', props.project?.name || '')
  if (hasImages) fd.append('has_images', 'true')
  fd.append('file', file)
  const art = await artifactApi.upload(fd)
  ElMessage.success('工件已保存')
  await loadArtifacts()
  emit('changed')
  return art
}

async function downloadArtifact(a) {
  if (!a?.id) return
  try {
    // 传入 file_path 供下载文件名补全扩展名（工件显示名往往没有后缀）
    const fname = await artifactApi.download(a.id, a.name, a.file_path)
    ElMessage.success(`已开始下载：${fname}`)
  } catch {
    /* 错误提示由 http 拦截器统一弹出 */
  }
}

async function removeArtifact(a) {
  if (!a?.id) return
  await artifactApi.remove(a.id)
  ElMessage.success('已删除')
  await loadArtifacts()
}

async function loadArtifacts() {
  if (!props.run) return
  artifacts.value = await artifactApi.list(props.run.id)
}

async function loadConnectors() {
  connectors.value = await connectorApi.list(0)
}

function patchStatus(status, meta = {}) {
  return workflowApi.patchStage(props.run.id, props.stage.id, { status, meta })
}

/* ---------- requirement ---------- */
const reqTab = ref('upload')
const reqFile = ref(null)
const pasteText = ref('')
const reqUrl = ref('')
const selConnectorId = ref(null)
const mcpTools = ref([])
const mcpTool = ref('')
const fetched = ref(null)
const pasting = ref(false)
const urlLoading = ref(false)
const connLoading = ref(false)
const saving = ref(false)
const summarizing = ref(false)
const summary = ref(null)
const genModel = ref('')   // 需求摘要使用的 AI 模型显示名（后端 /ai/summary 返回 model）
// 需求文档是否含图片：勾选「是」则保存后自动用多模态副模型识图规范化
const reqHasImages = ref(false)
const reqThinkSteps = ref([])
const thinkOpenReq = ref([])
let reqThinkTimer = null

const selConnector = computed(() =>
  connectors.value.find((c) => c.id === selConnectorId.value)
)

async function fetchPaste() {
  if (!pasteText.value.trim()) return ElMessage.warning('请先粘贴文本')
  pasting.value = true
  try {
    const r = await connectorApi.fetch({ kind: 'paste', cfg: {}, params: { text: pasteText.value, name: '需求-粘贴.txt' } })
    fetched.value = { text: r.text, name: r.name || '需求-粘贴.txt' }
  } finally {
    pasting.value = false
  }
}

async function fetchUrl() {
  if (!reqUrl.value.trim()) return ElMessage.warning('请填写 URL')
  urlLoading.value = true
  try {
    const r = await connectorApi.fetch({ kind: 'url_fetch', cfg: {}, params: { url: reqUrl.value } })
    fetched.value = { text: r.text, name: r.name || '需求-URL.txt' }
  } finally {
    urlLoading.value = false
  }
}

async function loadMcpTools() {
  mcpTools.value = []
  if (!selConnector.value) return
  const r = await connectorApi.mcpTools(selConnector.value.id)
  mcpTools.value = r.tools || []
}

async function fetchConnector() {
  const c = selConnector.value
  if (!c) return ElMessage.warning('请选择连接器')
  connLoading.value = true
  try {
    const params = {}
    if (c.kind === 'mcp') {
      if (!mcpTool.value) return ElMessage.warning('请选择要调用的 tool')
      params.tool = mcpTool.value
    } else if (reqUrl.value.trim()) {
      params.url = reqUrl.value
    }
    const r = await connectorApi.fetch({ kind: c.kind, cfg: c.cfg, params })
    fetched.value = { text: r.text, name: r.name || `${c.name}.txt` }
  } finally {
    connLoading.value = false
  }
}

async function saveRequirement() {
  saving.value = true
  try {
    let uploaded = null
    if (reqFile.value) {
      uploaded = await uploadArtifact(reqFile.value, 'requirement', '需求-' + reqFile.value.name, reqHasImages.value)
    } else if (fetched.value?.text) {
      uploaded = await uploadArtifact(makeTextFile(fetched.value.text, fetched.value.name || 'requirement.txt'), 'requirement', fetched.value.name || 'requirement.txt', reqHasImages.value)
    } else if (pasteText.value.trim()) {
      uploaded = await uploadArtifact(makeTextFile(pasteText.value, '需求-粘贴.txt'), 'requirement', '需求-粘贴.txt', reqHasImages.value)
    } else {
      ElMessage.warning('请先选择文件或拉取内容')
    }
    // 勾选「含图片」：后台已启动多模态规范化，轮询进度并在完成后刷新工件列表
    if (uploaded && reqHasImages.value) {
      startReqVisionPoll(props.run.id)
    }
  } finally {
    saving.value = false
  }
}

/* 轮询需求识图规范化进度：req_vision:{run_id}，done 后刷新工件列表并停止 */
function startReqVisionPoll(runId) {
  reqThinkSteps.value = []
  thinkOpenReq.value = ['reqVision']
  if (reqThinkTimer) clearInterval(reqThinkTimer)
  reqThinkTimer = setInterval(async () => {
    try {
      const d = await aiApi.progress(`req_vision:${runId}`)
      reqThinkSteps.value = d.steps || []
      // 轮询契约：exists && done 才算完成（key 未 start 时 get 返回 done=True 但 exists=False）
      if (d.exists && d.done) {
        clearInterval(reqThinkTimer)
        reqThinkTimer = null
        await loadArtifacts()
        if (d.error) ElMessage.warning(`识图规范化未完成（已降级）：${d.error}`)
        else ElMessage.success('识图规范化完成，已生成「需求文档（已规范化）」')
      }
    } catch { /* 轮询失败静默，下轮重试 */ }
  }, 2000)
}

/* 点击生成类按钮后通知看板刷新：后端接口入口即把阶段置 running，
   延迟 300ms 等 POST 先到达后端，刷新后看板/抽屉状态徽章立刻显示「进行中」。 */
function notifyRunning() {
  setTimeout(() => emit('changed'), 300)
}

async function genSummary() {
  if (!props.run) return
  summarizing.value = true
  startThink(`summary:${props.run.id}`)
  notifyRunning()
  try {
    const r = await aiApi.summary(props.run.id)
    summary.value = r.summary
    genModel.value = r.model || ''
    // 摘要已持久化到阶段 meta：通知看板刷新阶段数据，重开抽屉可回显
    emit('changed')
    ElMessage.success('需求摘要已生成并保存，关闭后重新打开仍可查看')
  } finally {
    stopThink()
    summarizing.value = false
  }
}

/* ---------- api_doc ---------- */
const apiTab = ref('upload')
const apiFile = ref(null)
const apiUrl = ref('')
const apiConnectorId = ref(null)
const apiFetched = ref(null)
const apiUrlLoading = ref(false)
const apiConnLoading = ref(false)
const savingApi = ref(false)

async function fetchApiUrl() {
  if (!apiUrl.value.trim()) return ElMessage.warning('请填写 URL')
  apiUrlLoading.value = true
  try {
    const r = await connectorApi.fetch({ kind: 'url_fetch', cfg: {}, params: { url: apiUrl.value } })
    apiFetched.value = { text: r.text, name: r.name || 'openapi.json' }
  } finally {
    apiUrlLoading.value = false
  }
}

async function fetchApiConnector() {
  const c = connectors.value.find((x) => x.id === apiConnectorId.value)
  if (!c) return ElMessage.warning('请选择连接器')
  apiConnLoading.value = true
  try {
    const params = apiUrl.value.trim() ? { url: apiUrl.value } : {}
    const r = await connectorApi.fetch({ kind: c.kind, cfg: c.cfg, params })
    apiFetched.value = { text: r.text, name: r.name || `${c.name}.txt` }
  } finally {
    apiConnLoading.value = false
  }
}

async function saveApiDoc() {
  savingApi.value = true
  try {
    if (apiFile.value) {
      await uploadArtifact(apiFile.value, 'api_doc', '接口-' + apiFile.value.name)
    } else if (apiFetched.value?.text) {
      const name = apiFetched.value.name || 'openapi.json'
      await uploadArtifact(makeTextFile(apiFetched.value.text, name), 'api_doc', name)
    } else {
      ElMessage.warning('请先选择文件或拉取内容')
    }
  } finally {
    savingApi.value = false
  }
}

async function skipStage() {
  await patchStatus('skipped')
  ElMessage.success('已跳过此阶段')
  emit('changed')
}

/* ---------- case_gen ---------- */
const generating = ref(false)
const regenerating = ref(false)
const generateMsg = ref('')
const caseGenModel = ref('')   // 生成用例使用的 AI 模型显示名（后端 /ai/generate-cases 返回 model）
const caseSets = ref([])
const latestTree = ref(null)
const showTreeTable = ref(false)
const caseType = ref('business')   // business=业务功能用例；api=接口测试用例
const exporting = ref('')          // '' / xmind / excel（导出中状态）
const reviewing = ref(false)       // 评审通过提交中
const execCases = computed(() => execResult.value?.summary?.cases || [])

/* 是否已上传接口文档（用于约束 case_gen 阶段只能选业务用例时禁用接口用例选项） */
const hasApiDoc = computed(() => apiArtifacts.value.length > 0)

/* 接口文档缺失时强制 caseType=business，避免误触发 API 用例生成（违反"仅需求文档不生成 API 用例"约束） */
watch(hasApiDoc, (has) => {
  if (!has && caseType.value === 'api') caseType.value = 'business'
}, { immediate: true })

// 生成进度（LLM 长耗时请求的可视反馈：渐近到 95% 等待完成，完成跳 100%）
const genProgress = ref(0)
let genTimer = null

function startProgress() {
  genProgress.value = 4
  clearInterval(genTimer)
  genTimer = setInterval(() => {
    genProgress.value = Math.min(95, genProgress.value + Math.max(0.5, (95 - genProgress.value) * 0.05))
  }, 600)
}

function finishProgress() {
  clearInterval(genTimer)
  genTimer = null
  genProgress.value = 100
  setTimeout(() => { genProgress.value = 0 }, 600)
}

/* ---------- 思考过程（后端 task_progress 轮询，可折叠） ---------- */
const thinkSteps = ref([])          // [{ts, text}]
const thinkOpen = ref(['think'])    // el-collapse 展开状态（默认展开）
let thinkTimer = null
let thinkKey = ''

function startThink(key) {
  // 仅当切换任务 key 时才清空历史步骤（同 key 重入如切卡恢复时保留旧步骤，避免闪「等待…」）
  if (thinkKey !== key) thinkSteps.value = []
  thinkKey = key
  stopThink(false)
  thinkTimer = setInterval(async () => {
    try {
      const d = await aiApi.progress(key)
      if (d?.steps) thinkSteps.value = d.steps
    } catch { /* 轮询失败静默，下轮重试 */ }
  }, 1500)
}

function stopThink(pull = true) {
  if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null }
  if (pull && thinkKey) {
    // 结束时最后拉一次，保证末尾步骤（结果/耗时）完整展示
    aiApi.progress(thinkKey)
      .then((d) => { thinkSteps.value = d.steps || thinkSteps.value })
      .catch(() => {})
  }
}

/* 用例集类型：business / api（旧数据无标记时默认 business） */
function csType(cs) {
  return cs?.gen_meta?.case_type || cs?.content?.case_type || 'business'
}

/* 当前选中类型的用例集（按版本倒序），与 radio 联动，两种类型互不混淆 */
const typedCaseSets = computed(() => caseSets.value.filter((cs) => csType(cs) === caseType.value))

async function loadCaseSets() {
  if (!props.run) return
  caseSets.value = await aiApi.caseSets(props.run.id)
  // 只显示当前选中类型的用例树；无则置空。不能用 || caseSets[0].content 兜底，
  // 否则 business 无数据时会误显示 api 类型的树（两种类型串页）
  latestTree.value = typedCaseSets.value[0]?.content || null
}

function previewCaseSet(cs) {
  latestTree.value = cs.content
  showTreeTable.value = false
}

/* 当前类型最新用例集是否已评审通过（approved）——代表已人工检查过 */
const currentReviewed = computed(() => typedCaseSets.value[0]?.status === 'approved')

/* 按当前用例类型导出对应用例集（业务/接口互不混淆），复用 /ai/export */
async function exportCases(format) {
  if (!typedCaseSets.value.length) {
    return ElMessage.warning(`尚无${caseType.value === 'api' ? '接口测试' : '业务功能'}用例集，请先生成`)
  }
  exporting.value = format
  try {
    const r = await aiApi.exportCases({
      run_id: props.run.id,
      format,
      project: props.project?.name || '',
      case_type: caseType.value
    })
    if (r?.artifact_id) {
      await artifactApi.download(r.artifact_id, r.name)
      ElMessage.success('导出成功，已开始下载')
    }
  } finally {
    exporting.value = ''
  }
}

/* 评审通过：按当前用例类型把最新用例集标记为 approved（已检查），作为下一步门槛 */
async function approveCases() {
  if (!typedCaseSets.value.length) {
    return ElMessage.warning(`尚无${caseType.value === 'api' ? '接口测试' : '业务功能'}用例集，请先生成`)
  }
  reviewing.value = true
  try {
    const r = await aiApi.review({ run_id: props.run.id, result: 'approved', case_type: caseType.value, reviewer: '' })
    ElMessage.success(r.message || '评审通过，已标记为检查过')
    await loadCaseSets()
    emit('changed')
  } finally {
    reviewing.value = false
  }
}

async function generateCases() {
  generating.value = true
  generateMsg.value = ''
  startProgress()
  startThink(`case_gen:${props.run.id}`)
  notifyRunning()
  try {
    const r = await aiApi.generateCases({ run_id: props.run.id, project: props.project?.name || '', case_type: caseType.value })
    const data = r.data || r
    caseGenModel.value = r.model || ''
    if (data?.tree) {
      latestTree.value = data.tree
      generateMsg.value = r.message || '用例生成成功'
    }
    await loadCaseSets()
    await loadArtifacts()  // 刷新用例树 + 生成日志工件
    emit('changed')
  } finally {
    finishProgress()
    stopThink()
    generating.value = false
  }
}

async function regenerate() {
  try {
    const { value } = await ElMessageBox.prompt('请输入重新生成的原因（作为上下文）', '重新生成', {
      inputPlaceholder: '如：缺少边界值用例 / 接口字段覆盖不全…',
      confirmButtonText: '生成',
      cancelButtonText: '取消'
    })
    regenerating.value = true
    startProgress()
    startThink(`case_gen:${props.run.id}`)
    notifyRunning()
    try {
      const r = await aiApi.regenerate({ run_id: props.run.id, project: props.project?.name || '', reason: value || '', case_type: caseType.value })
      if (r?.data?.tree) latestTree.value = r.data.tree
      ElMessage.success(r.message || '已重新生成')
      await loadCaseSets()
      emit('changed')
    } finally {
      finishProgress()
      stopThink()
      regenerating.value = false
    }
  } catch {
    /* 用户取消 */
  }
}

// 切换用例类型时，预览同步切到该类型的最新用例集
watch(caseType, () => {
  latestTree.value = typedCaseSets.value[0]?.content || null
  showTreeTable.value = false
})

/* ---------- skill（独立 AI 处理卡片） ---------- */
const skills = ref([])
const selSkillId = ref('')
const skillInputsText = ref('')
const skillRunning = ref(false)
const skillResult = ref(null)

/** 模板/实例绑定的 skill_id（存在 meta.skill_id，由模板设计预选带入） */
const boundSkillId = computed(() => props.stage?.meta?.skill_id || '')
const boundSkillName = computed(() => {
  const s = skills.value.find((x) => x.id === boundSkillId.value)
  return s ? s.name : boundSkillId.value
})

async function loadSkills() {
  skills.value = await aiApi.skills()
  // 步骤已绑定 skill 时，下拉预选该 skill（模板设计带过来，或上次运行后持久化）
  if (boundSkillId.value && skills.value.some((s) => s.id === boundSkillId.value)) {
    selSkillId.value = boundSkillId.value
  }
}

/** 选择即持久化：把选中的 skill_id 写入阶段 meta（复用 PATCH meta 合并） */
async function persistSkillBind() {
  if (!selSkillId.value) return
  try {
    await patchStatus('', { skill_id: selSkillId.value })
    emit('changed')
    ElMessage.success('Skill 绑定已更新')
  } catch {
    /* 错误提示由拦截器统一弹出 */
  }
}

async function runSkill() {
  if (!selSkillId.value) return ElMessage.warning('请先选择 AI 能力')
  let inputs = {}
  if (skillInputsText.value.trim()) {
    try {
      inputs = JSON.parse(skillInputsText.value)
    } catch {
      return ElMessage.warning('运行参数不是合法 JSON')
    }
  }
  skillRunning.value = true
  skillResult.value = null
  try {
    const r = await aiApi.runSkill({ run_id: props.run.id, skill_id: selSkillId.value, inputs, project: props.project?.name || '' })
    skillResult.value = r
    ElMessage.success(r.message || '执行完成')
    await loadArtifacts()
    emit('changed')
    // 运行成功也把 skill 绑定持久化，避免"模板没绑、抽屉里才选"的情况丢失
    if (boundSkillId.value !== selSkillId.value) persistSkillBind()
  } finally {
    skillRunning.value = false
  }
}

/* ---------- mcp（独立平台取数卡片） ---------- */
const mcpConnectorId = ref(null)
const mcpLoadingTools = ref(false)
const mcpTools2 = ref([])
const mcpTool2 = ref('')
const mcpArgsText = ref('{}')
const mcpFetching = ref(false)
const mcpFetchResult = ref(null)

const mcpConnectors = computed(() => connectors.value.filter((c) => c.kind === 'mcp'))
const selMcpConnector = computed(() => connectors.value.find((c) => c.id === mcpConnectorId.value))

async function loadMcpTools2() {
  mcpTools2.value = []
  if (!selMcpConnector.value) return ElMessage.warning('请选择 MCP 连接器')
  mcpLoadingTools.value = true
  try {
    const r = await connectorApi.mcpTools(selMcpConnector.value.id)
    mcpTools2.value = r.tools || []
  } finally {
    mcpLoadingTools.value = false
  }
}

async function runMcpFetch() {
  const c = selMcpConnector.value
  if (!c) return ElMessage.warning('请选择 MCP 连接器')
  if (!mcpTool2.value) return ElMessage.warning('请选择要调用的 tool')
  let args = {}
  try {
    args = JSON.parse(mcpArgsText.value || '{}')
  } catch {
    return ElMessage.warning('tool 参数不是合法 JSON')
  }
  mcpFetching.value = true
  mcpFetchResult.value = null
  try {
    const r = await connectorApi.fetch({ kind: 'mcp', cfg: c.cfg, params: { tool: mcpTool2.value, args } })
    mcpFetchResult.value = r.text
    const name = r.name || `mcp_${mcpTool2.value}.txt`
    await uploadArtifact(makeTextFile(r.text, name), 'mcp_data', name)
    ElMessage.success('已拉取并保存为工件')
    emit('changed')
  } finally {
    mcpFetching.value = false
  }
}

/* ---------- auto_gen ---------- */
const autoGenerating = ref(false)
const autoResult = ref(null)

function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// 轮询 auto_gen:{run_id} 进度直到 done：生成已完成（成功/失败都会置 done），
// 结果由 watch(stage.meta.auto_result) 兜底回显，失败原因由进度 error 展示
async function waitAutoGenDone() {
  const key = `auto_gen:${props.run.id}`
  for (let i = 0; i < 300; i++) {
    const d = await aiApi.progress(key).catch(() => null)
    // 必须 exists 才算：key 尚未被后台线程 start 时 get 返回 done=True 但 exists=False
    if (d && d.exists && d.done) return
    if (d && !d.exists && i > 10) return  // 防御：一直无任务（异常），避免空等
    await _sleep(2000)
  }
}

async function autoGenerate() {
  // 前置校验：已上传接口文档时必须已有「评审通过」的接口测试用例集，否则提示先去评审
  if (apiArtifacts.value.length > 0) {
    const hasApprovedApi = caseSets.value.some((cs) => csType(cs) === 'api' && cs.status === 'approved')
    if (!hasApprovedApi) {
      ElMessage.warning('请先评审接口用例：在生成用例页选中「接口测试用例」后点「评审通过」')
      return
    }
  }
  autoGenerating.value = true
  autoResult.value = null
  startProgress()
  startThink(`auto_gen:${props.run.id}`)
  notifyRunning()
  try {
    // 后端已改后台线程模式：接口立即返回，生成在后台跑，前端轮询进度直到完成
    const r = await aiApi.autoGenerate({ run_id: props.run.id, project_id: props.project?.id })
    ElMessage.success(r.message || '自动化生成已启动')
    await waitAutoGenDone()
    await loadArtifacts()  // 刷新生成脚本 + 生成日志工件
    emit('changed')        // 看板阶段状态已落库（success/failed），通知父组件刷新
  } catch {
    /* 错误提示由拦截器统一弹出；这里同步看板阶段状态（running/failed 由后端落库），
       超时场景后端可能仍在跑，刷新后可看到「进行中」，完成后再刷新即为终态 */
    notifyRunning()
  } finally {
    finishProgress()
    stopThink()
    autoGenerating.value = false
  }
}

/* ---------- execute ---------- */
const envChecking = ref(false)
const executing = ref(false)
const envItems = ref([])
const execResult = ref(null)

const allureUrl = computed(() =>
  props.project && props.run ? allureReportUrl(props.project.name, props.run.id) : ''
)

async function envCheck() {
  if (!props.project) return
  envChecking.value = true
  try {
    const r = await execApi.envCheck(props.project.id)
    envItems.value = r.items || []
  } finally {
    envChecking.value = false
  }
}

async function execRun() {
  if (!props.project || !props.run) return
  // 先确保拿到用例模块名（离开页面再进 latestTree 会丢，重新拉取用例集）
  if (!latestTree.value) await loadCaseSets()
  const module = latestTree.value?.module || caseSets.value[0]?.content?.module
  if (!module) {
    ElMessage.warning('未找到用例模块名，请先在「生成用例」阶段生成用例')
    return
  }
  executing.value = true
  startProgress()
  startThink(`execute:${props.run.id}`)
  notifyRunning()   // 后端 POST /run 入口已置 execute 阶段 running，看板立刻显示「执行中」
  try {
    const r = await execApi.run({ run_id: props.run.id, module, project_id: props.project.id })
    const first = r.result || r
    if (first.status === 'running' && first.message && first.message.includes('轮询')) {
      // 后台执行模式：拿 execution_id 轮询直到结束
      const execId = r.execution_id
      execResult.value = { status: 'running', summary: {}, message: '已提交后台执行，正在轮询结果…' }
      const deadline = Date.now() + 31 * 60 * 1000
      while (Date.now() < deadline) {
        await new Promise(res => setTimeout(res, 3000))
        const d = await execApi.detail(execId)
        execResult.value = d
        if (d.status && d.status !== 'running') break
      }
      execResult.value = execResult.value || { status: 'failed', error_log: '轮询超时' }
    } else {
      execResult.value = first
    }
    envItems.value = execResult.value?.env_check?.items || envItems.value
    await loadArtifacts()  // 刷新执行日志工件
    emit('changed')   // 执行结束：同步看板阶段终态（passed -> 已完成 / failed -> 失败）
  } finally {
    finishProgress()
    stopThink()
    executing.value = false
  }
}

/* ---------- 执行失败 AI 修复闭环 ---------- */
const fixing = ref(false)
const fixResult = ref(null)

async function runAutoFix() {
  if (!props.project || !props.run) return
  fixing.value = true
  fixResult.value = null
  startProgress()
  startThink(`auto_gen:${props.run.id}`)
  const key = `auto_gen:${props.run.id}`
  try {
    // 后台线程模式：接口立即返回，随后轮询进度直到 done（修复含自动重新执行，可能需数分钟）
    await aiApi.autoFix({
      run_id: props.run.id,
      execution_id: 0,   // 0=自动取最新一次执行
      project_id: props.project.id
    })
    const deadline = Date.now() + 20 * 60 * 1000
    let d = null
    while (Date.now() < deadline) {
      await new Promise(res => setTimeout(res, 2000))
      try {
        d = await aiApi.progress(key)
        thinkSteps.value = d.steps || []
      } catch { /* 轮询失败静默重试 */ }
      if (d?.done) break
    }
    if (d?.error) {
      ElMessage.error(`AI 修复失败：${d.error}`)
    } else {
      ElMessage.success('AI 修复流程已完成（含自动重新执行测试），结果见执行详情')
    }
    // 从阶段 meta 取 AI 分析结论（auto_fix 服务持久化在 auto_gen 阶段）
    try {
      const sts = await workflowApi.stages(props.run.id)
      const autoSt = sts.find((s) => s.stage_type === 'auto_gen')
      const meta = autoSt?.meta || {}
      if (meta.fix_analysis) {
        fixResult.value = {
          message: d?.error ? `AI 修复失败：${d.error}` : 'AI 修复流程已完成',
          analysis: meta.fix_analysis,
          fix_round: meta.fix_rounds || 0,
          regenerated: true
        }
      }
    } catch { /* 阶段数据获取失败不影响主流程 */ }
    // 回显最新执行结果（修复后自动执行的那次）
    try {
      const execs = await execApi.runs(props.run.id)
      if (execs.length) execResult.value = await execApi.detail(execs[0].id)
    } catch { /* 忽略 */ }
    await loadArtifacts()
    emit('changed')
  } finally {
    finishProgress()
    stopThink()
    fixing.value = false
  }
}

function openAllure() {
  window.open(allureUrl.value, '_blank')
}

/* ---------- 通用阶段操作：无手动完成/失败操作，状态由步骤自动控制 ---------- */

/* ---------- 打开时重置 ---------- */
function onReviewChanged() {
  // ReviewPanel 内部操作完成后，同步刷新阶段状态与用例集
  emit('changed')
  loadCaseSets()
}

/* 打开序号：每次打开/切换卡片递增；回显阶段只允许最新一次调用生效，
   避免「打开 + 切换卡片」同一 tick 双触发时旧调用覆盖新阶段的回显 */
let openSeq = 0

function onOpen() {
  const seq = ++openSeq
  loading.value = true
  Promise.all([loadArtifacts(), loadConnectors(), loadSkills()])
    .then(() => {
      const t = props.stage?.stage_type
      // 需要用例集数据的阶段：预览/评审/自动化生成（回显结果）/执行（取模块名）
      if (['case_gen', 'case_review', 'auto_gen', 'execute'].includes(t)) {
        return loadCaseSets()
      }
    })
    .then(() => {
      if (seq !== openSeq) return  // 已被更新的打开调用取代（快速切换卡片），丢弃过期回显
      // 自动化生成结果持久化在阶段 meta 里：离开页面再进也能回显
      if (props.stage?.stage_type === 'auto_gen' && props.stage.meta?.auto_result) {
        autoResult.value = props.stage.meta.auto_result
      }
      // 需求摘要同样持久化在阶段 meta：重开抽屉 / 刷新页面后回显，不再丢失
      if (props.stage?.stage_type === 'requirement' && props.stage.meta?.summary) {
        summary.value = props.stage.meta.summary
      }
      // 生成进行中恢复：以 task_progress key（exists && !done）为唯一事实，函数内部自判，
      // 不依赖易过期的 stage.status。切卡/刷新/重开抽屉通用：进行中 → 恢复进度条+思考过程，
      // 已结束 → 直接跳过（此时结果已由 meta / 用例集列表回显）。
      if (props.stage?.stage_type === 'auto_gen') resumeAutoGen()
      if (props.stage?.stage_type === 'case_gen') resumeCaseGen()
    })
    .finally(() => {
      if (seq === openSeq) loading.value = false
    })
}

// 刷新/重开抽屉/切卡时后台生成仍在跑 → 恢复进度反馈并等待完成（结果由 meta 兜底回显）。
// 事实来源 = task_progress key（exists && !done），不依赖 stage.status；任一拉取抖动都不中断恢复。
async function resumeAutoGen() {
  if (props.stage?.stage_type !== 'auto_gen') return false
  const d = await aiApi.progress(`auto_gen:${props.run.id}`).catch(() => null)
  if (!d || !d.exists || d.done) return false  // 无进行中任务（未开始/已完成）→ 不恢复
  autoGenerating.value = true
  startProgress()
  startThink(`auto_gen:${props.run.id}`)
  try {
    await waitAutoGenDone()
    await loadArtifacts()
    emit('changed')
  } catch { /* 轮询抖动/个别接口失败：不打断恢复，结果由下一次刷新兜底 */ }
  finishProgress()
  stopThink()
  autoGenerating.value = false
  return true
}

// 刷新/重开抽屉/切卡时 case_gen 生成仍在后端跑（同步长请求，前端断连后结果仍会落库）：
// 以 progress key 为进行中事实恢复进度条 + 思考过程，轮询直到「任务 done / 新版本落库 / 阶段退出 running」。
async function resumeCaseGen() {
  if (props.stage?.stage_type !== 'case_gen') return false
  const key = `case_gen:${props.run.id}`
  const d = await aiApi.progress(key).catch(() => null)
  if (!d || !d.exists || d.done) return false  // 无进行中任务（未开始/已完成）→ 不恢复
  const initialVersion = typedCaseSets.value[0]?.version || 0
  generating.value = true
  startProgress()
  startThink(key)
  const deadline = Date.now() + 6 * 60 * 1000  // LLM 长调用最长约 5 分钟，留余量
  try {
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 2000))
      // 1) 后端任务 done（finish）= 真完成（比 stage.status 可靠：生成结束会走到 pending_review）
      const d2 = await aiApi.progress(key).catch(() => null)
      if (d2 && d2.exists && d2.done) break
      // 2) 新版本用例集落库 = 生成完成
      try {
        await loadCaseSets()
        if ((typedCaseSets.value[0]?.version || 0) > initialVersion) break
      } catch { /* 拉取抖动继续轮询 */ }
      // 3) 阶段退出 running 兜底
      const stages = await aiApi.stages(props.run.id).catch(() => null)
      const st = stages?.find((s) => s.stage_type === 'case_gen')
      if (st && st.status !== 'running') break
    }
  } finally {
    finishProgress()
    stopThink()
    generating.value = false
    emit('changed')  // 刷新看板，卡片从「进行中」恢复实际状态
  }
  return true
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      // 打开：触发回显/数据加载（与抽屉 @open 等价）
      onOpen()
      return
    }
    fetched.value = null
    apiFetched.value = null
    summary.value = null
    genModel.value = ''
    envItems.value = []
    execResult.value = null
    autoResult.value = null
    fixResult.value = null
    thinkSteps.value = []
    stopThink(false)
    if (reqThinkTimer) { clearInterval(reqThinkTimer); reqThinkTimer = null }
  }
)

/* 已打开状态下切换「不同阶段」卡片：重新加载数据/回显。
   注意：同一阶段 stages 刷新（父组件按 id 替换同 id 引用）时 id 不变，不会重复加载，
   避免一键执行/生成过程中内容反复重载闪烁；旧回显靠下方 meta 兜底 watch 同步。 */
watch(
  () => props.stage?.id,
  (n, o) => {
    if (props.modelValue && n !== o) onOpen()
  }
)

/* autoGenerate 接口成功后 emit('changed') → 父组件 refresh → loadStages 拉新 stages →
   selectedStage 被 watch 同步为新对象（含最新 meta.auto_result）。
   兜底回显：selectedStage 变化时若 autoResult 为空但 meta.auto_result 有值，自动回显，
   避免用户在 5 分钟等待期间关抽屉清空 autoResult 后重开看不到生成结果。 */
watch(
  () => props.stage?.meta?.auto_result,
  (v) => {
    if (v && !autoResult.value && props.stage?.stage_type === 'auto_gen') {
      autoResult.value = v
    }
  }
)

function formatJson(obj) {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

function formatDate(s) {
  if (!s) return ''
  return String(s).replace('T', ' ').slice(0, 16)
}

function csStatus(s) {
  return { generated: '已生成', approved: '已批准', returned: '已打回', reviewed: '已评审' }[s] || s
}
</script>

<style scoped>
/* 卡片下方内嵌展示面板：全宽 + 上限居中 + 长内容内部滚动兜底 */
.stage-panel {
  max-width: 1200px;
  margin: 0 auto;
  background: var(--card, #fff);
  border: 1px solid var(--border);
  border-radius: var(--radius-card, 12px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  padding: 0 20px 18px;
  max-height: 70vh;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0 12px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--card, #fff);
  z-index: 1;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text, #333);
}

/* 打开时淡入 */
.panel-fade-enter-active,
.panel-fade-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.panel-fade-enter-from,
.panel-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.stage-detail {
  padding: 4px 2px;
}

.stage-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.meta-error {
  font-size: 12px;
  color: var(--danger);
  width: 100%;
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin: 14px 0 8px;
}

.mt8 {
  margin-top: 8px;
}

.mb8 {
  margin-bottom: 8px;
}

.row-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.fetched-box {
  margin-top: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  padding: 8px;
}

.fetched-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  margin-bottom: 6px;
}

.fetched-preview {
  max-height: 140px;
  font-size: 11px;
}

.result-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.result-item {
  display: flex;
  gap: 10px;
  font-size: 13px;
  align-items: flex-start;
}

.result-item label {
  color: var(--text-secondary);
  flex-shrink: 0;
  width: 64px;
}

.result-item .path {
  font-family: Consolas, Menlo, monospace;
  font-size: 12px;
  word-break: break-all;
}

.tc-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.case-set-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  padding: 8px 10px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
}

/* 生成进度条 */
.gen-progress {
  border: 1px dashed var(--primary);
  border-radius: var(--radius-control);
  padding: 10px 12px;
  background: var(--primary-light, rgba(75, 63, 227, 0.05));
}

.gen-progress .form-hint {
  margin-top: 6px;
}

/* 思考过程折叠面板 */
.think-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  background: transparent;
  border-bottom: none;
}

.think-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
  border-bottom: none;
}

.think-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 4px;
}

.think-title {
  font-size: 12px;
  color: var(--text-secondary);
}

.think-list {
  max-height: 180px;
  overflow-y: auto;
  background: var(--secondary);
  border-radius: var(--radius-control);
  padding: 6px 10px;
}

.think-line {
  display: flex;
  gap: 8px;
  font-size: 12px;
  line-height: 1.8;
  font-family: Consolas, Menlo, monospace;
}

.think-ts {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.think-text {
  color: var(--text);
  word-break: break-all;
  white-space: pre-wrap;
}

/* AI 修复区块 */
.fix-box {
  border: 1px solid var(--warning, #e6a23c);
  border-radius: var(--radius-control);
  padding: 10px 12px;
  background: rgba(230, 162, 60, 0.04);
}

.case-set-item:hover {
  background: var(--primary-light);
}

.summary-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.stat {
  background: var(--secondary);
  border-radius: var(--radius-control);
  padding: 10px 8px;
  text-align: center;
}

.stat b {
  display: block;
  font-size: 20px;
  color: var(--text);
}

.stat span {
  font-size: 12px;
  color: var(--text-secondary);
}

.stat.ok b {
  color: #0aa368;
}

.stat.fail b {
  color: var(--danger);
}

.stat.skip b {
  color: var(--warning);
}

.drawer-footer {
  margin-top: 20px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
