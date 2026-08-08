<template>
  <div class="page-container err-page">
    <div class="err-card">
      <div class="err-code">403</div>
      <div class="err-title">无访问权限</div>
      <div class="err-desc">您没有权限访问该页面，请联系管理员分配相应权限。</div>
      <el-button type="primary" @click="$router.push('/')">返回工作台</el-button>
    </div>
  </div>
</template>

<style scoped>
.err-page {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.err-card {
  text-align: center;
  padding: 40px;
  background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border);
  border-radius: 12px;
}
.err-code {
  font-size: 56px;
  font-weight: 700;
  color: var(--el-color-primary);
  line-height: 1;
}
.err-title {
  font-size: 20px;
  font-weight: 600;
  margin: 12px 0 6px;
}
.err-desc {
  color: var(--itsm-text-muted);
  margin-bottom: 20px;
}
</style>
