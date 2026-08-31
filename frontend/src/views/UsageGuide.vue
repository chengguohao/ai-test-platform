<template>
  <div class="page">
    <div class="page-header">
      <h3 class="page-title">使用说明</h3>
    </div>

    <div class="panel">
      <h4 class="panel-title">AI 测试工作流平台 · 快速上手</h4>
      <p class="muted">
        平台以「项目 → 流程实例 → 阶段」为主线，串起 需求 → 接口 → 生成用例 → 评审 → 自动化 → 执行报告
        的全流程闭环，由 AI（Skill + MCP 实据）驱动减少手工编排。
      </p>

      <el-collapse v-model="activeNames">
        <el-collapse-item title="① 创建项目" name="1">
          <ol class="guide-list">
            <li>进入「项目列表」，点击右上角「新建项目」。</li>
            <li>填写项目名称、描述，以及执行引擎配置（JSON）：被测系统 base_url、登录账号密码、pytest 项目目录、python、allure 路径、生成目录。</li>
            <li>「AI 模型」下拉选择该项目使用的模型配置（在左侧「AI 配置」管理）；不选则用全局默认。</li>
          </ol>
        </el-collapse-item>

        <el-collapse-item title="② 设计流程模板" name="2">
          <ol class="guide-list">
            <li>在项目卡片点击「模板设计」，进入流程画布。</li>
            <li>从左侧「阶段类型库」点击「+」或拖拽卡片加入画布，支持上移/下移/复制/删除/启用禁用。</li>
            <li>展开卡片可编辑阶段名称、数据来源（upload / paste / url_fetch / mcp / connector）与来源配置。</li>
            <li>点击「保存模板」；模板可切换、可删除。</li>
          </ol>
        </el-collapse-item>

        <el-collapse-item title="③ 运行工作流看板" name="3">
          <ol class="guide-list">
            <li>在项目卡片点击「打开工作台」，选择或新建一个流程实例。</li>
            <li>看板以横排阶段卡片 + 连接线展示进度：进行中阶段紫色脉冲、已完成段紫色流动虚线、打回红色徽章、跳过置灰。</li>
            <li>点击阶段卡片打开详情抽屉，按阶段类型执行：上传需求/生成摘要、拉取接口文档、生成用例树、评审导出/打回/通过、生成自动化用例、环境自检与执行测试。</li>
            <li>底部「下一步」把当前进行中阶段置为已完成并推进到下一阶段。</li>
          </ol>
        </el-collapse-item>

        <el-collapse-item title="④ 用例评审与执行报告" name="4">
          <ol class="guide-list">
            <li>「用例评审」页可独立选择项目+流程实例，执行导出 XMind/Excel、打回、回传、通过等评审闭环。</li>
            <li>「执行报告」页可做环境自检、执行 pytest 测试、查看执行历史与错误日志，并内嵌 Allure 报告。</li>
          </ol>
        </el-collapse-item>

        <el-collapse-item title="⑤ 连接器与 Skill 能力" name="5">
          <ol class="guide-list">
            <li><b>Skill 能力</b>：左侧「Skill 能力」页查看平台内置 AI 能力（需求摘要 / 用例生成 / 自动化生成）的提示词与输出契约；「模板设计」的 AI 处理步骤可预先绑定某个 Skill，实例中运行也默认用它。</li>
            <li><b>AI 配置</b>：左侧「AI 配置」页可维护多套大模型（名称 / 接口地址 / Key / 模型 / 温度）；新建项目时选择绑定其中一套，未选则用全局默认。</li>
            <li><b>连接器用途</b>：
              <ul class="guide-list">
                <li>paste：需求 / 知识库文字直接粘贴存为工件（最常用的免文件方式）；</li>
                <li>url_fetch：抓取网页，如在线 Swagger / OpenAPI 接口文档、需求页面；</li>
                <li>http：调自研平台 REST 接口拉数据（可配请求头 / JSON 解析）；</li>
                <li>mcp：对接外部公司平台，列出其暴露的 tools 后拉真实数据存为工件；</li>
                <li>smtp：评审结果等邮件通知（push 场景，需发信邮箱配置）；</li>
                <li>local：读取服务端本地文件。</li>
              </ul>
            </li>
            <li>在「需求上传 / 接口文档 / 平台取数」等阶段里按需选用连接器；均可「测试连接」验证。</li>
          </ol>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const activeNames = ref(['1', '2', '3', '4', '5'])
</script>

<style scoped>
.guide-list {
  padding-left: 18px;
  margin: 8px 0;
  line-height: 1.9;
  color: var(--text);
  font-size: 13px;
}
</style>
