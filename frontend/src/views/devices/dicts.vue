<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">设备字典配置</h2>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="设备类型" name="types">
          <DictTable resource="types" :show-type="false" />
        </el-tab-pane>
        <el-tab-pane label="品牌管理" name="brands">
          <DictTable resource="brands" :show-type="false" />
        </el-tab-pane>
        <el-tab-pane label="网络类型" name="network-types">
          <DictTable resource="network-types" :show-type="false" />
        </el-tab-pane>
        <el-tab-pane label="自定义字段" name="custom-fields">
          <DictTable resource="custom-fields" :show-type="true" />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import DictTable from './DictTable.vue'

const route = useRoute()
const activeTab = ref('types')

watch(
  () => route.query.tab,
  (t) => {
    if (t && ['types', 'brands', 'network-types', 'custom-fields'].includes(String(t))) {
      activeTab.value = String(t)
    }
  },
  { immediate: true },
)

onMounted(() => {
  /* tabs 懒加载由 DictTable 自行拉取 */
})
</script>
