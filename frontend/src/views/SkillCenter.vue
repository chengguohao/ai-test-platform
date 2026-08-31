<template>
  <div class="page">
    <div class="page-header">
      <h3 class="page-title">Skill 能力</h3>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="mb12"
      title="Skill 是平台内置的 AI 能力（固定提示词 + 输出契约 + 校验器），由后端注册保证输出可靠。可在流程模板的「AI 处理」步骤中预先绑定。"
    />

    <div v-loading="loading" class="skill-grid">
      <el-empty v-if="!loading && !skills.length" description="暂无注册的 Skill" />
      <article v-for="s in skills" :key="s.id" class="skill-card" @click="openDetail(s.id)">
        <div class="skill-head">
          <div class="skill-icon"><el-icon><MagicStick /></el-icon></div>
          <div class="skill-info">
            <div class="skill-name">{{ s.name }}</div>
            <div class="skill-id">{{ s.id }}</div>
          </div>
          <el-tag size="small" :type="s.kind === 'code' ? 'warning' : 'success'" effect="plain">
            {{ s.kind === 'code' ? '代码生成' : 'JSON 结构化' }}
          </el-tag>
        </div>
        <p class="skill-desc">{{ s.desc || '暂无描述' }}</p>
        <div class="skill-foot">
          <span class="muted">v{{ s.version }}</span>
          <el-button size="small" text type="primary">查看详情</el-button>
        </div>
      </article>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawerVisible" :title="detail?.name ? `Skill 详情 · ${detail.name}` : 'Skill 详情'" size="640px">
      <div v-if="detail" class="skill-detail">
        <div class="meta-row">
          <span>ID：{{ detail.id }}</span>
          <span>版本：v{{ detail.version }}</span>
          <span>类型：{{ detail.kind === 'code' ? '代码生成' : 'JSON 结构化' }}</span>
          <span>失败重试：最多 {{ detail.max_retries }} 次</span>
        </div>
        <p class="skill-desc">{{ detail.desc }}</p>

        <div class="block-title">系统提示词（固定规则，反幻觉核心）</div>
        <pre class="code-block">{{ detail.system_prompt }}</pre>

        <template v-if="detail.output_schema">
          <div class="block-title">输出契约（JSON Schema）</div>
          <pre class="code-block">{{ JSON.stringify(detail.output_schema, null, 2) }}</pre>
        </template>
        <el-alert v-else type="info" :closable="false" title="该 Skill 输出 Python 代码（pytest ApiCase 脚本），无 JSON 契约" class="mt8" />
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { MagicStick, Refresh } from '@element-plus/icons-vue'
import { aiApi } from '@/api'

const skills = ref([])
const loading = ref(false)
const drawerVisible = ref(false)
const detail = ref(null)

async function load() {
  loading.value = true
  try {
    skills.value = await aiApi.skills()
  } finally {
    loading.value = false
  }
}

async function openDetail(id) {
  drawerVisible.value = true
  detail.value = null
  detail.value = await aiApi.skillDetail(id)
}

onMounted(load)
</script>

<style scoped>
.mb12 {
  margin-bottom: 12px;
}

.mt8 {
  margin-top: 8px;
}

.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  min-height: 160px;
}

.skill-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 18px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.skill-card:hover {
  border-color: rgba(75, 63, 227, 0.35);
  box-shadow: 0 8px 20px rgba(27, 29, 42, 0.08);
}

.skill-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.skill-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, #4b3fe3, #7c73ea);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.skill-info {
  flex: 1;
  min-width: 0;
}

.skill-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.skill-id {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: Consolas, Menlo, monospace;
}

.skill-desc {
  margin: 12px 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  flex: 1;
}

.skill-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.skill-detail .meta-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  margin: 16px 0 8px;
}
</style>
