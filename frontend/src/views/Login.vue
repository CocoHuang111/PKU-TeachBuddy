<template>
  <div class="login-page">
    <header class="nav">
      <div class="brand"><img src="/brand/iteachbuddy-logo-light.svg" alt="iTeachBuddy" /></div>
    </header>

    <div class="panel">
      <h1>{{ isSso ? '统一身份认证' : '教师登录' }}</h1>
      <p class="lead">
        {{
          isSso
            ? '使用北京大学统一身份认证进入系统。本地账号不会自动合并。'
            : '内测阶段使用本系统账号登录。管理员需由安全命令创建。'
        }}
      </p>

      <div v-if="isSso" class="sso-box">
        <el-button type="primary" class="submit" :loading="loading" @click="onPkuLogin">
          使用北京大学统一身份认证
        </el-button>
        <p v-if="!authState.config.pku_sso_ready" class="hint">
          服务端尚未配置官方认证地址，按钮会返回明确错误，不会假装已经接通。
        </p>
      </div>

      <el-tabs v-else v-model="tab" class="tabs">
        <el-tab-pane label="登录" name="login">
          <el-form :model="loginForm" label-position="top" @submit.prevent="onLogin">
            <el-alert v-if="loginError" :title="loginError" type="error" show-icon :closable="false" class="form-error" role="alert" />
            <el-form-item label="学校">
              <el-input
                v-model="loginForm.school"
                maxlength="80"
                placeholder="与注册时一致；尚未登记学校的账号可留空"
              />
            </el-form-item>
            <el-form-item label="工号">
              <el-input v-model="loginForm.username" maxlength="32" placeholder="请输入工号" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="loginForm.password"
                type="password"
                show-password
                maxlength="64"
                placeholder="请输入密码"
                @keyup.enter="onLogin"
              />
            </el-form-item>
            <el-button type="primary" :loading="loading" class="submit" @click="onLogin">
              登录
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane v-if="authState.config.registration_enabled" label="注册" name="register">
          <el-form :model="registerForm" label-position="top">
            <el-alert v-if="registerError" :title="registerError" type="error" show-icon :closable="false" class="form-error" role="alert" />
            <el-form-item label="学校">
              <el-input v-model="registerForm.school" maxlength="80" placeholder="例如：北京大学" />
            </el-form-item>
            <el-form-item label="工号">
              <el-input v-model="registerForm.username" maxlength="32" placeholder="3–32 位字母、数字或点/下划线/连字符" />
            </el-form-item>
            <el-form-item label="姓名">
              <el-input v-model="registerForm.display_name" maxlength="40" placeholder="例如：张明" />
            </el-form-item>
            <el-form-item v-if="authState.config.invite_required" label="邀请码">
              <el-input v-model="registerForm.invite_code" maxlength="64" placeholder="由管理员发放" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="registerForm.password"
                type="password"
                show-password
                maxlength="64"
                :placeholder="`至少 ${authState.config.password_min_length} 位`"
              />
            </el-form-item>
            <el-form-item label="确认密码">
              <el-input
                v-model="registerForm.confirm_password"
                type="password"
                show-password
                maxlength="64"
                placeholder="再输入一次"
                @keyup.enter="onRegister"
              />
            </el-form-item>
            <el-button type="primary" :loading="loading" class="submit" @click="onRegister">
              注册并登录
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '../api/client'
import { authState, setUser } from '../authStore'
import { authErrorMessage } from '../utils/authErrors'

const router = useRouter()
const route = useRoute()
const tab = ref('login')
const loading = ref(false)
const loginError = ref('')
const registerError = ref('')
const isSso = computed(() => authState.config.auth_mode === 'pku_sso')

const loginForm = reactive({
  school: '',
  username: '',
  password: '',
})

const registerForm = reactive({
  school: '',
  username: '',
  display_name: '',
  invite_code: '',
  password: '',
  confirm_password: '',
})

function goNext() {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  router.replace(redirect && redirect.startsWith('/') ? redirect : '/qa')
}

async function onLogin() {
  if (loading.value) return
  loginError.value = ''
  if (!loginForm.username.trim() || !loginForm.password) {
    loginError.value = '请填写工号和密码'
    return
  }
  loading.value = true
  try {
    const data = await authApi.login({
      school: loginForm.school.trim(),
      username: loginForm.username.trim(),
      password: loginForm.password,
    })
    setUser(data.user)
    ElMessage.success(`欢迎回来，${data.user.display_name || data.user.username}`)
    goNext()
  } catch (error) {
    loginError.value = authErrorMessage(error, 'login')
  } finally {
    loading.value = false
  }
}

async function onRegister() {
  if (loading.value) return
  registerError.value = ''
  const form = registerForm
  if (!form.school.trim() || !form.username.trim() || !form.display_name.trim()) {
    registerError.value = '请填写学校、工号和姓名'
    return
  }
  if (form.school.trim().length > 80) {
    registerError.value = '学校名称不能超过 80 字'
    return
  }
  if (!/^[A-Za-z0-9._-]{3,32}$/.test(form.username.trim())) {
    registerError.value = '工号须为 3–32 位字母、数字、点、下划线或连字符'
    return
  }
  if (!form.password || !form.confirm_password) {
    registerError.value = '请填写密码和确认密码'
    return
  }
  if (form.password.length < authState.config.password_min_length) {
    registerError.value = `密码至少需要 ${authState.config.password_min_length} 位`
    return
  }
  if (authState.config.invite_required && !form.invite_code.trim()) {
    registerError.value = '请填写邀请码'
    return
  }
  if (form.password !== form.confirm_password) {
    registerError.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  try {
    const data = await authApi.register({
      school: form.school.trim(),
      username: form.username.trim(),
      display_name: form.display_name.trim(),
      password: form.password,
      confirm_password: form.confirm_password,
      invite_code: form.invite_code || undefined,
    })
    setUser(data.user)
    ElMessage.success('注册成功')
    goNext()
  } catch (error) {
    registerError.value = authErrorMessage(error, 'register')
  } finally {
    loading.value = false
  }
}

async function onPkuLogin() {
  loading.value = true
  try {
    const data = await authApi.pkuStart()
    if (data.authorize_url) {
      window.location.href = data.authorize_url
      return
    }
    ElMessage.error('未返回认证地址')
  } catch {
    /* 错误已由 axios 拦截器提示 */
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.form-error {
  margin-bottom: 16px;
}
.login-page {
  min-height: 100vh;
  background: #f5f7fa;
}

.nav {
  height: 56px;
  background: #7b1113;
  display: flex;
  align-items: center;
  padding: 0 20px;
}

.brand {
  display: flex;
  align-items: center;
}
.brand img { display: block; width: 170px; height: auto; }

.panel {
  width: min(440px, calc(100% - 32px));
  margin: 48px auto 40px;
  background: #fff;
  border: 1px solid #e8eaed;
  border-radius: 10px;
  padding: 28px 28px 32px;
}

.panel h1 {
  margin: 0;
  font-size: 22px;
  color: #303133;
}

.lead {
  margin: 8px 0 18px;
  font-size: 13px;
  color: #909399;
}

.tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}

.submit {
  width: 100%;
  margin-top: 8px;
}

.hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}
</style>
