<template>
  <div class="page">
    <h1>用户管理</h1>
    <div class="toolbar">
      <el-input v-model="q" placeholder="搜索学校 / 工号 / 姓名" clearable @keyup.enter="load" />
      <el-button type="primary" @click="load">搜索</el-button>
    </div>
    <el-table :data="items" v-loading="loading">
      <el-table-column label="学校" min-width="140">
        <template #default="{ row }">{{ row.school || '—' }}</template>
      </el-table-column>
      <el-table-column label="工号" width="140">
        <template #default="{ row }">{{ row.username || row.staff_id || '—' }}</template>
      </el-table-column>
      <el-table-column prop="display_name" label="显示名称" width="140" />
      <el-table-column prop="role" label="角色" width="80" />
      <el-table-column prop="status" label="状态" width="80" />
      <el-table-column label="认证来源" width="140">
        <template #default="{ row }">{{ (row.providers || []).join(', ') }}</template>
      </el-table-column>
      <el-table-column label="任务数" width="160">
        <template #default="{ row }">
          评 {{ row.task_counts?.eval_tasks || 0 }} /
          纲 {{ row.task_counts?.syllabus_tasks || 0 }} /
          问 {{ row.task_counts?.qa_sessions || 0 }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="320">
        <template #default="{ row }">
          <el-button text type="primary" @click="toggleStatus(row)">
            {{ row.status === 'active' ? '停用' : '恢复' }}
          </el-button>
          <el-button text type="primary" @click="toggleRole(row)">
            {{ row.role === 'admin' ? '取消管理员' : '设为管理员' }}
          </el-button>
          <el-button
            v-if="authState.config.auth_mode === 'local' && (row.providers || []).includes('local')"
            text
            type="primary"
            @click="resetPassword(row)"
          >
            重置密码
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      class="pager"
      layout="prev, pager, next"
      :total="total"
      :page-size="pageSize"
      v-model:current-page="page"
      @current-change="load"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '../../api/client'
import { authState } from '../../authStore'

const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const q = ref('')

async function load() {
  loading.value = true
  try {
    const data = await adminApi.users({ q: q.value || undefined, page: page.value, page_size: pageSize })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function toggleStatus(row) {
  if (row.status === 'active') await adminApi.disableUser(row.id)
  else await adminApi.enableUser(row.id)
  ElMessage.success('已更新')
  load()
}

async function toggleRole(row) {
  const role = row.role === 'admin' ? 'user' : 'admin'
  await adminApi.setRole(row.id, role)
  ElMessage.success('角色已更新')
  load()
}

async function resetPassword(row) {
  const { value } = await ElMessageBox.prompt('输入新密码', '重置密码', { inputType: 'password' })
  await adminApi.resetPassword(row.id, value)
  ElMessage.success('密码已重置，该用户现有登录已失效')
}

onMounted(load)
</script>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; }
.toolbar { display: flex; gap: 8px; margin: 12px 0 16px; width: 480px; }
.pager { margin-top: 16px; }
</style>
