<template>
  <el-container class="shell" direction="vertical">
    <el-dialog
      v-model="followupVisible"
      width="min(540px, 92vw)"
      append-to-body
      align-center
      @closed="closeFollowup"
    >
      <template #header><span class="eval-followup-title">{{ followupKind === 'syllabus' ? '大纲已加入优化队列！' : '视频已加入评估队列！' }}</span></template>
      <p>{{ followupKind === 'syllabus' ? '当前大纲已进入优化队列，处理可能耗时较长，请耐心等待' : '当前视频正在排队中，预计耗时较长，请耐心等待' }}</p>
      <p class="eval-followup-hint">{{ followupKind === 'syllabus' ? '大纲长度及服务器负载会影响实际耗时。关闭标签页不会停止已提交的优化，进度可在历史任务中查看。' : '视频时长及服务器负载会影响实际耗时。关闭标签页不会停止已入队的解析，进度可在历史任务中查看。' }}</p>
      <p class="eval-followup-question">{{ followupKind === 'syllabus' ? '是否在大纲优化完成后发送邮件通知？' : '是否在报告完成后发送邮件通知？' }}</p>
      <p v-if="mailStatus === 'waiting_service'" class="eval-followup-hint">通知申请已保存；邮件服务尚未配置，暂不能发送。报告仍可在系统内查看。</p>
      <p v-else-if="mailStatus === 'pending'" class="eval-followup-success"><el-icon><CircleCheckFilled /></el-icon>已开启完成邮件通知。</p>
      <p v-else-if="mailStatus === 'sent'">报告通知已发送。</p>
      <el-button v-if="!['pending', 'sent', 'waiting_service'].includes(mailStatus)" :loading="mailSaving" @click="enableReportMail">是，完成后通知我</el-button>
      <el-button v-if="!['pending', 'sent', 'waiting_service'].includes(mailStatus)" @click="mailDeclined = true">{{ mailDeclined ? '已选择暂不需要' : '暂不需要' }}</el-button>
      <template #footer>
        <el-button type="primary" @click="goToFeature('/qa')">前往智能问答</el-button>
        <el-button @click="goToFeature(followupKind === 'syllabus' ? '/evaluation' : '/syllabus')">{{ followupKind === 'syllabus' ? '前往视频评估' : '前往大纲优化' }}</el-button>
      </template>
    </el-dialog>
    <header class="nav">
      <div class="brand">
        <img class="brand-logo" src="/brand/iteachbuddy-logo-light.svg" alt="iTeachBuddy" />
        <img class="brand-mark" src="/brand/iteachbuddy-mark-light.svg" alt="iTeachBuddy" />
      </div>
      <div class="nav-right">
        <el-menu
          :default-active="$route.path"
          :ellipsis="false"
          router
          mode="horizontal"
          class="menu"
        >
          <el-menu-item index="/qa">智能问答</el-menu-item>
          <el-menu-item index="/evaluation">教学评估</el-menu-item>
          <el-menu-item index="/syllabus">大纲优化</el-menu-item>
          <el-menu-item index="/profile">我的</el-menu-item>
        </el-menu>
        <div class="who">
          <router-link v-if="isAdmin()" class="admin-link" to="/admin">后台</router-link>
          <el-button class="logout" text @click="onLogout">退出</el-button>
        </div>
      </div>
    </header>

      <el-main class="main" :class="{ flush: $route.path === '/qa' || $route.path === '/evaluation' || $route.path === '/syllabus' }">
        <router-view v-slot="{ Component }">
          <keep-alive include="QA,Evaluation">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
  </el-container>
</template>

<script setup>
import { onMounted } from 'vue'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { authApi } from '../api/client'
import { clearAuth, isAdmin } from '../authStore'
import { resetQa } from '../qaStore'
import {
  closeFollowup,
  enableReportMail,
  followupVisible,
  followupKind,
  goToFeature,
  mailDeclined,
  mailSaving,
  mailStatus,
  restorePendingFollowup,
} from '../evalFollowupStore'

const router = useRouter()

onMounted(() => {
  restorePendingFollowup()
})

async function onLogout() {
  closeFollowup()
  try {
    await authApi.logout()
  } catch {
    /* 本地清掉即可 */
  }
  clearAuth()
  resetQa()
  router.replace('/login')
}
</script>

<style scoped>
.shell {
  height: 100vh;
}

.nav {
  height: 56px;
  flex-shrink: 0;
  background: #7b1113;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.brand {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}
.brand-logo { display: block; width: 170px; height: auto; }
.brand-mark { display: none; width: 34px; height: 34px; }
@media (max-width: 900px) {
  .brand-logo { display: none; }
  .brand-mark { display: block; }
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.who {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  flex-shrink: 0;
}
.admin-link {
  color: rgba(255, 255, 255, 0.8);
  font-size: 13px;
  text-decoration: none;
  margin-right: 8px;
}
.admin-link:hover {
  color: #fff;
}
.logout {
  color: rgba(255, 255, 255, 0.72) !important;
  padding: 0 8px;
}
.logout:hover {
  color: #fff !important;
}

.menu {
  flex: 0 0 auto;
  width: auto;
  background: transparent;
  border-bottom: none;
  height: 56px;
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: transparent;
  --el-menu-text-color: rgba(255, 255, 255, 0.78);
  --el-menu-hover-text-color: #fff;
  --el-menu-active-color: #fff;
}
.menu :deep(.el-menu-item) {
  height: 56px;
  line-height: 56px;
  font-size: 14px;
  border-bottom: 2px solid transparent !important;
  padding: 0 18px;
  overflow: visible;
}
.menu :deep(.el-menu-item:hover) {
  background: transparent;
}
.menu :deep(.el-menu-item.is-active) {
  background: transparent !important;
  font-weight: 600;
  border-bottom-color: #fff !important;
}

.main {
  padding: 16px;
  background: #f5f7fa;
  overflow-y: auto;
}
.main.flush {
  padding: 0;
  overflow: hidden;
  background: #fff;
}
</style>

<style>
.eval-followup-title { font-size: 22px; font-weight: 700; }
.eval-followup-question { font-size: 18px; font-weight: 700; }
.eval-followup-success { color: #529b2e; display: flex; align-items: center; gap: 6px; }
.eval-followup-hint {
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}
</style>
