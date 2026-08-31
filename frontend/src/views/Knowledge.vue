<template>
  <div class="page kb-page">
    <!-- 顶部：标题 + 统计 + 搜索 -->
    <div class="kb-hero">
      <div class="kb-hero-left">
        <div class="kb-title">
          <span class="kb-title-dot" />
          <h3 class="page-title">知识库</h3>
          <el-tag size="small" effect="plain" round class="kb-title-tag">存档</el-tag>
        </div>
        <div class="muted kb-sub">
          已评审通过的业务功能用例 / 接口测试用例存档，供后续生成用例时自动参考（模块级去重取最新）
        </div>
      </div>
      <div class="kb-hero-right">
        <div class="kb-stats">
          <div class="kb-stat">
            <b>{{ stats.total }}</b><span>总条目</span>
          </div>
          <div class="kb-stat">
            <b>{{ stats.business }}</b><span>业务功能</span>
          </div>
          <div class="kb-stat">
            <b>{{ stats.api }}</b><span>接口用例</span>
          </div>
          <div class="kb-stat">
            <b>{{ stats.projects }}</b><span>项目</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 列表工具条：列表上方、右侧（查询框 + 查询按钮） -->
    <div class="kb-toolbar">
      <el-input
        v-model="search"
        placeholder="按项目名称模糊查询…"
        clearable
        class="kb-search"
        :prefix-icon="Search"
        @keyup.enter="load"
        @clear="load"
      />
      <el-button type="primary" :icon="Search" :loading="loading" @click="load">查询</el-button>
    </div>

    <!-- 主体：卡片网格 -->
    <div v-loading="loading" class="kb-grid-wrap">
      <div v-if="!loading && !entries.length" class="kb-empty">
        <el-empty description="暂无知识库记录">
          <el-button type="primary" @click="$router.push('/')">去项目看板，完成需求后点击「本次需求完成」</el-button>
        </el-empty>
      </div>

      <div v-else class="kb-grid">
        <article v-for="(e, i) in entries" :key="e.id" class="kb-card" :style="{ '--i': i }">
          <div class="kb-card-accent" :class="e.case_type === 'api' ? 'is-api' : ''" />
          <div class="kb-card-head">
            <div class="kb-card-title-row">
              <span class="kb-project-name" :title="e.project_name">{{ e.project_name }}</span>
              <el-tag
                size="small"
                effect="plain"
                round
                :type="e.case_type === 'api' ? 'warning' : 'primary'"
              >{{ typeLabel(e.case_type) }}</el-tag>
            </div>
            <div class="kb-module">{{ moduleOf(e) || '未知模块' }}</div>
          </div>

          <div class="kb-card-body">
            <div class="kb-meta-line">
              <span class="kb-meta">
                <el-icon><Tickets /></el-icon>用例集 v{{ e.case_version }}
              </span>
              <span class="kb-meta">
                <el-icon><FolderOpened /></el-icon>{{ groupCount(e) }} 组
              </span>
              <span class="kb-meta">
                <el-icon><Checked /></el-icon>{{ caseCount(e) }} 条用例
              </span>
            </div>
            <div class="kb-meta-line muted">
              <span class="kb-meta">
                <el-icon><EditPen /></el-icon>修改 {{ e.mod_time || '-' }}
              </span>
              <span class="kb-meta">
                <el-icon><Clock /></el-icon>保存 {{ formatDate(e.created_at) }}
              </span>
            </div>
          </div>

          <div class="kb-card-foot">
            <el-button size="small" type="primary" plain @click="openView(e)">查看用例</el-button>
            <el-button size="small" type="danger" plain :icon="Delete" @click="remove(e)">删除</el-button>
          </div>
        </article>
      </div>
    </div>

    <!-- 查看：二级弹窗展示用例树快照（复用 CaseTree） -->
    <el-dialog
      v-model="viewVisible"
      :title="viewTitle"
      width="840px"
      destroy-on-close
      top="6vh"
      class="kb-view-dialog"
    >
      <div v-if="viewEntry" class="view-meta panel">
        <div class="view-meta-main">
          <span class="view-project">{{ viewEntry.project_name }}</span>
          <el-tag
            size="small"
            effect="plain"
            round
            :type="viewEntry.case_type === 'api' ? 'warning' : 'primary'"
          >{{ typeLabel(viewEntry.case_type) }}</el-tag>
          <span class="pill pill-primary">用例集 v{{ viewEntry.case_version }}</span>
          <span class="pill">模块：{{ moduleOf(viewEntry) || '未知' }}</span>
        </div>
        <div class="view-meta-sub muted">
          <span>修改时间：{{ viewEntry.mod_time || '-' }}</span>
          <span>保存时间：{{ formatDate(viewEntry.created_at) }}</span>
          <span>{{ groupCount(viewEntry) }} 组 · {{ caseCount(viewEntry) }} 条用例</span>
        </div>
      </div>
      <CaseTree v-if="viewEntry" :tree="viewEntry.content" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Search, Delete, Tickets, FolderOpened, Checked, EditPen, Clock } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import CaseTree from '@/components/CaseTree.vue'
import { knowledgeApi } from '@/api'

const entries = ref([])
const loading = ref(false)
const search = ref('')
const viewVisible = ref(false)
const viewEntry = ref(null)

const typeLabel = (t) => (t === 'api' ? '接口测试用例' : '业务功能用例')
const viewTitle = computed(() =>
  viewEntry.value
    ? `${viewEntry.value.project_name} · ${typeLabel(viewEntry.value.case_type)}`
    : '用例明细'
)

/* 顶部统计：总条目 / 业务 / 接口 / 覆盖项目数 */
const stats = computed(() => {
  const s = { total: entries.value.length, business: 0, api: 0, projects: new Set() }
  for (const e of entries.value) {
    if (e.case_type === 'api') s.api += 1
    else s.business += 1
    s.projects.add(e.project_id)
  }
  return { ...s, projects: s.projects.size, total: s.total }
})

const moduleOf = (e) => (e.content && e.content.module) || ''
const groupCount = (e) => ((e.content && e.content.groups) || []).length
const caseCount = (e) =>
  ((e.content && e.content.groups) || []).reduce((n, g) => n + ((g.cases || []).length), 0)

function formatDate(s) {
  if (!s) return '-'
  return String(s).replace('T', ' ').slice(0, 19)
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (search.value.trim()) params.q = search.value.trim()
    entries.value = await knowledgeApi.list(params)
  } finally {
    loading.value = false
  }
}

function openView(row) {
  viewEntry.value = row
  viewVisible.value = true
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.project_name} · ${typeLabel(row.case_type)}（保存于 ${formatDate(row.created_at)}）」？仅删知识库快照，不影响原用例集。`,
      '删除知识库记录',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await knowledgeApi.remove(row.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
/* ---------- 顶部 ---------- */
.kb-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.kb-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.kb-title-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary), #7c73ea);
  box-shadow: 0 0 0 4px var(--primary-light);
}

.kb-title-tag {
  margin-left: 4px;
}

.kb-sub {
  margin-top: 6px;
  font-size: 13px;
  max-width: 560px;
  line-height: 1.5;
}

.kb-hero-right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

/* 统计胶囊 */
.kb-stats {
  display: flex;
  gap: 14px;
}

.kb-stat {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 8px 16px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  text-align: center;
  min-width: 76px;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.kb-stat:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(27, 29, 42, 0.08);
}

.kb-stat b {
  font-size: 20px;
  color: var(--text);
  line-height: 1.2;
}

.kb-stat span {
  font-size: 11px;
  color: var(--text-secondary);
}

/* 列表工具条：列表上方，从左往右排列 */
.kb-toolbar {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.kb-search {
  width: 260px;
}

/* ---------- 卡片网格 ---------- */
.kb-grid-wrap {
  min-height: 220px;
}

.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.kb-card {
  position: relative;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 18px 18px 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
  animation: kb-enter 0.35s ease both;
  animation-delay: calc(var(--i) * 40ms);
}

@keyframes kb-enter {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.kb-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 30px rgba(27, 29, 42, 0.1);
  border-color: rgba(75, 63, 227, 0.35);
}

/* 顶部左侧品牌色条装饰 */
.kb-card-accent {
  position: absolute;
  left: 0;
  top: 0;
  width: 4px;
  height: 100%;
  background: linear-gradient(180deg, var(--primary), #a19bf0);
  opacity: 0.85;
}

.kb-card-accent.is-api {
  background: linear-gradient(180deg, #d99a12, #efaa17);
}

.kb-card-head {
  padding-left: 4px;
}

.kb-card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.kb-project-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-module {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

/* 卡身信息 */
.kb-card-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-left: 4px;
}

.kb-meta-line {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
}

.kb-meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text); /* 第一行强调 */
}

.muted .kb-meta {
  color: var(--text-secondary);
}

/* 卡脚操作 */
.kb-card-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px dashed var(--border);
  padding-top: 12px;
}

/* ---------- 空态 ---------- */
.kb-empty {
  padding: 60px 0;
}

/* ---------- 查看弹窗 ---------- */
.view-meta {
  margin: 0 0 14px;
  padding: 14px 16px;
}

.view-meta-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.view-project {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.view-meta-sub {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 12px;
  margin-top: 10px;
}
</style>