import { defineStore } from 'pinia'
import { projectApi } from '@/api'

/**
 * 全局应用状态（项目列表缓存，供多页面共享）
 */
export const useAppStore = defineStore('app', {
  state: () => ({
    projects: [],
    projectsLoaded: false
  }),
  getters: {
    projectById: (state) => (id) => state.projects.find((p) => String(p.id) === String(id))
  },
  actions: {
    async loadProjects(force = false) {
      if (this.projectsLoaded && !force) return this.projects
      this.projects = await projectApi.list()
      this.projectsLoaded = true
      return this.projects
    },
    async reloadProjects() {
      this.projects = await projectApi.list()
      this.projectsLoaded = true
      return this.projects
    }
  }
})
