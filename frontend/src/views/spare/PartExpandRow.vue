<template>
  <div v-loading="loading" class="expand-detail">
    <template v-if="detail">
      <el-descriptions :column="cols" border size="small">
        <el-descriptions-item :label="label('spare', 'code', '编码')">{{ detail.code || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'category', '分类')">{{ detail.category || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'brand', '品牌')">{{ detail.brand || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'model', '型号')">{{ detail.model || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'specification', '规格')">{{ detail.specification || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'unit', '单位')">{{ detail.unit || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'manufacturer', '厂家')">{{ detail.manufacturer || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'serial_number', '序列号')">{{ detail.serial_number || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'reference_price', '参考价')">
          {{ Number(detail.reference_price || 0).toLocaleString() }}
        </el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'warranty_months', '质保月数')">{{ detail.warranty_months || 0 }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'min_stock', '库存下限')">{{ detail.min_stock }}</el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'total_stock', '库存数量')">
          <el-tag size="small" :type="detail.stock_alert ? 'danger' : 'success'">
            {{ detail.total_stock }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="label('spare', 'remark', '备注')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">库存明细</el-divider>
      <el-table v-if="detail.stocks?.length" :data="detail.stocks" size="small" border>
        <el-table-column prop="location" :label="label('spare_stock', 'location', '库位')" min-width="120" />
        <el-table-column prop="quantity" :label="label('spare_stock', 'quantity', '数量')" width="80" />
        <el-table-column prop="unit_price" :label="label('spare_stock', 'unit_price', '单价')" width="100">
          <template #default="{ row: tr }">{{ Number(tr.unit_price || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="updated_at" :label="label('spare_stock', 'updated_at', '更新时间')" width="140" />
      </el-table>
      <el-empty v-else description="暂无库存" :image-size="50" />

      <el-divider content-position="left">采购入库</el-divider>
      <el-table v-if="detail.purchases?.length" :data="detail.purchases" size="small" border>
        <el-table-column prop="supplier_name" :label="label('purchase_order', 'supplier_name', '供应商')" min-width="110" />
        <el-table-column prop="quantity" :label="label('purchase_order', 'quantity', '数量')" width="70" />
        <el-table-column prop="total" :label="label('purchase_order', 'total', '总额')" width="100">
          <template #default="{ row: tr }">{{ Number(tr.total || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="purchase_date" :label="label('purchase_order', 'purchase_date', '采购日期')" width="100" />
        <el-table-column prop="operator" :label="label('purchase_order', 'operator', '经办人')" width="90" />
      </el-table>
      <el-empty v-else description="暂无采购记录" :image-size="50" />

      <el-divider content-position="left">销售出库</el-divider>
      <el-table v-if="detail.sales?.length" :data="detail.sales" size="small" border>
        <el-table-column prop="customer_name" :label="label('sales_order', 'customer_name', '客户')" min-width="110" />
        <el-table-column prop="quantity" :label="label('sales_order', 'quantity', '数量')" width="70" />
        <el-table-column prop="total" :label="label('sales_order', 'total', '总额')" width="100">
          <template #default="{ row: tr }">{{ Number(tr.total || 0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="sales_date" :label="label('sales_order', 'sales_date', '销售日期')" width="100" />
        <el-table-column prop="operator" :label="label('sales_order', 'operator', '经办人')" width="90" />
      </el-table>
      <el-empty v-else description="暂无销售记录" :image-size="50" />

      <div class="expand-actions">
        <el-button v-if="user.hasPerm('spare:edit')" type="primary" size="small" @click="emit('edit')">
          编辑
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, reactive } from 'vue'
import { useUserStore } from '@/stores/user'
import { useMobile } from '@/utils/useMobile'
import { fetchSparePart, type SparePart } from '@/api/spare'
import { entityFieldLabel, fetchEntityMetas, type EntityMeta } from '@/api/meta'

const { isMobile } = useMobile()
// 移动端降为 2 列，避免每项 <100px
const cols = computed(() => (isMobile.value ? 2 : 4))

const props = defineProps<{ row: Record<string, unknown> }>()
const emit = defineEmits<{ (e: 'edit'): void }>()

const user = useUserStore()
const loading = ref(false)
const detail = ref<SparePart | null>(null)
const metadata = reactive<Record<string, EntityMeta>>({})
const label = (entity: string, key: string, fallback: string) =>
  entityFieldLabel(metadata[entity], key, fallback)

async function load() {
  loading.value = true
  try {
    detail.value = await fetchSparePart(props.row.id as number)
  } catch { /* toast */ } finally {
    loading.value = false
  }
}

// 列表刷新后行对象被替换 → 自动重取详情保持新鲜
watch(() => props.row, () => { load() })

load()
fetchEntityMetas(['spare', 'spare_stock', 'purchase_order', 'sales_order'])
  .then((metas) => Object.assign(metadata, metas))
</script>

<style scoped>
.expand-detail { padding: 4px 8px 8px; }
.expand-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; }
</style>
