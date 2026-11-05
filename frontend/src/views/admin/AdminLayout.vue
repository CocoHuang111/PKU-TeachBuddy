<template>
  <el-container class="shell" direction="vertical">
    <header class="nav">
      <div class="brand">
        <img class="brand-logo" src="/brand/iteachbuddy-logo-light.svg" alt="iTeachBuddy" />
        <span>· 管理后台</span>
      </div>
      <div class="nav-right">
        <el-menu :default-active="$route.path" router mode="horizontal" class="menu">
          <el-menu-item index="/admin/overview">概览</el-menu-item>
          <el-menu-item index="/admin/users">用户</el-menu-item>
          <el-menu-item index="/admin/tasks">任务</el-menu-item>
          <el-menu-item index="/admin/audit">审计</el-menu-item>
        </el-menu>
        <router-link class="back" to="/qa">返回前台</router-link>
      </div>
    </header>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.shell { height: 100vh; }
.nav {
  height: 56px;
  background: #7b1113;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}
.brand { color: #fff; font-weight: 700; display: flex; align-items: center; gap: 8px; }
.brand-logo { display: block; width: 170px; height: auto; }
.nav-right { display: flex; align-items: center; gap: 16px; }
.menu {
  background: transparent;
  border-bottom: none;
  --el-menu-bg-color: transparent;
  --el-menu-text-color: rgba(255,255,255,.78);
  --el-menu-active-color: #fff;
  --el-menu-hover-bg-color: transparent;
}
.back { color: rgba(255,255,255,.85); text-decoration: none; font-size: 13px; }
.main { background: #f5f7fa; }
</style>
