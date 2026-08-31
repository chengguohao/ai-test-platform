<template>
  <el-container class="app-shell">
    <!-- 左侧菜单 -->
    <el-aside width="228px" class="app-aside">
      <div class="brand" @click="$router.push('/')">
        <div class="brand-logo">AI</div>
        <div class="brand-name">AI 测试工作流平台</div>
      </div>
      <el-menu
        :default-active="activeMenu"
        class="app-menu"
        router
        @select="onMenuSelect"
      >
        <el-menu-item index="/">
          <el-icon><Folder /></el-icon>
          <span>项目列表</span>
        </el-menu-item>
        <el-menu-item index="/skills">
          <el-icon><MagicStick /></el-icon>
          <span>Skill 能力</span>
        </el-menu-item>
        <el-menu-item index="/ai-models">
          <el-icon><Cpu /></el-icon>
          <span>AI 配置</span>
        </el-menu-item>
        <el-menu-item index="/connectors">
          <el-icon><Connection /></el-icon>
          <span>连接器设置</span>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><Collection /></el-icon>
          <span>知识库</span>
        </el-menu-item>
        <el-menu-item index="/usage">
          <el-icon><QuestionFilled /></el-icon>
          <span>使用说明</span>
        </el-menu-item>
      </el-menu>
      <div class="aside-footer">
        <el-tag size="small" effect="plain" round>v0.1.0</el-tag>
      </div>
    </el-aside>

    <el-container class="app-main">
      <!-- 顶栏：当前页标题 -->
      <el-header height="56px" class="app-header">
        <div class="header-left">
          <h2 class="header-title">{{ pageTitle }}</h2>
        </div>
        <div class="header-right">
          <slot name="header-actions" />
        </div>
      </el-header>
      <el-main class="app-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const pageTitle = computed(() => route.meta?.title || 'AI 测试工作流平台')

// 高亮当前菜单：项目详情页统一高亮「项目列表」
const activeMenu = computed(() => {
  if (route.path === '/usage') return '/usage'
  if (route.path === '/connectors') return '/connectors'
  if (route.path === '/knowledge') return '/knowledge'
  if (route.path === '/skills') return '/skills'
  if (route.path === '/ai-models') return '/ai-models'
  return '/'
})

function onMenuSelect(index) {
  router.push(index)
}
</script>

<style scoped>
.app-shell {
  height: 100vh;
  overflow: hidden;
}

/* ---------- 侧边栏 ---------- */
.app-aside {
  background: var(--card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 16px;
  cursor: pointer;
}

.brand-logo {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(135deg, #4b3fe3, #7c73ea);
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.5px;
}

.brand-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text);
  line-height: 1.3;
}

.app-menu {
  border-right: none;
  padding: 6px 10px;
  flex: 1;
}

.app-menu :deep(.el-menu-item) {
  height: 42px;
  line-height: 42px;
  border-radius: 10px;
  margin-bottom: 4px;
  color: var(--text-secondary);
  font-size: 14px;
}

.app-menu :deep(.el-menu-item:hover) {
  background: var(--secondary);
}

.app-menu :deep(.el-menu-item.is-active) {
  background: var(--primary-light);
  color: var(--primary);
  font-weight: 600;
}

.aside-footer {
  padding: 14px 20px;
  text-align: left;
}

/* ---------- 主区 ---------- */
.app-main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-header {
  background: var(--card);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  color: var(--text);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.app-content {
  flex: 1;
  overflow: auto;
  padding: 0;
}
</style>
