<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">备件管理</h2>
    </div>

    <el-card shadow="never" class="tabs-card">
      <el-tabs v-model="activeTab" class="module-tabs">
        <!-- ==================== 备件档案 ==================== -->
        <el-tab-pane label="备件档案" name="archive" lazy>
          <div class="tab-toolbar">
            <div class="filter-row">
              <el-input v-model="partQuery.search" placeholder="搜索名称 / 编码 / 品牌 / 型号" clearable
                class="filter-search" @keyup.enter="reload('part')" @clear="reload('part')" />
              <el-select v-model="partQuery.category" placeholder="分类" clearable class="filter-item"
                @change="reload('part')">
                <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
              </el-select>
              <el-button type="primary" plain :icon="Search" @click="reload('part')">查询</el-button>
            </div>
            <el-button v-if="user.hasPerm('spare:add')" type="primary" :icon="Plus" @click="openPartCreate">
              新增备件
            </el-button>
          </div>

          <DataTable
            ref="partTableRef"
            :columns="partColumns"
            :fetch-data="fetchSpareParts"
            :query="partQuery"
            row-key="id"
            @row-click="openPartDetail"
          />

          <!-- 备件详情抽屉 -->
          <el-drawer v-model="partDetailVisible" :title="partDetail ? partDetail.name : ''" size="620px"
            destroy-on-close>
            <template v-if="partDetail">
              <el-descriptions :column="2" border size="small">
                <el-descriptions-item label="编码">{{ partDetail.code || '-' }}</el-descriptions-item>
                <el-descriptions-item label="分类">{{ partDetail.category || '-' }}</el-descriptions-item>
                <el-descriptions-item label="品牌">{{ partDetail.brand || '-' }}</el-descriptions-item>
                <el-descriptions-item label="型号">{{ partDetail.model || '-' }}</el-descriptions-item>
                <el-descriptions-item label="规格">{{ partDetail.specification || '-' }}</el-descriptions-item>
                <el-descriptions-item label="单位">{{ partDetail.unit || '-' }}</el-descriptions-item>
                <el-descriptions-item label="厂家">{{ partDetail.manufacturer || '-' }}</el-descriptions-item>
                <el-descriptions-item label="序列号">{{ partDetail.serial_number || '-' }}</el-descriptions-item>
                <el-descriptions-item label="参考价">
                  {{ Number(partDetail.reference_price || 0).toLocaleString() }}
                </el-descriptions-item>
                <el-descriptions-item label="保修期(月)">{{ partDetail.warranty_months || 0 }}</el-descriptions-item>
                <el-descriptions-item label="安全库存">{{ partDetail.min_stock }}</el-descriptions-item>
                <el-descriptions-item label="总库存">
                  <el-tag size="small" :type="partDetail.stock_alert ? 'danger' : 'success'">
                    {{ partDetail.total_stock }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="备注" :span="2">{{ partDetail.remark || '-' }}</el-descriptions-item>
              </el-descriptions>

              <el-divider content-position="left">库存明细</el-divider>
              <el-table v-if="partDetail.stocks?.length" :data="partDetail.stocks" size="small" border>
                <el-table-column prop="location" label="库位" min-width="120" />
                <el-table-column prop="quantity" label="数量" width="80" />
                <el-table-column prop="unit_price" label="单价" width="100">
                  <template #default="{ row }">{{ Number(row.unit_price || 0).toLocaleString() }}</template>
                </el-table-column>
                <el-table-column prop="updated_at" label="更新时间" width="140" />
              </el-table>
              <el-empty v-else description="暂无库存" :image-size="50" />

              <el-divider content-position="left">采购入库</el-divider>
              <el-table v-if="partDetail.purchases?.length" :data="partDetail.purchases" size="small" border>
                <el-table-column prop="supplier_name" label="供应商" min-width="110" />
                <el-table-column prop="quantity" label="数量" width="70" />
                <el-table-column prop="total" label="总额" width="100">
                  <template #default="{ row }">{{ Number(row.total || 0).toLocaleString() }}</template>
                </el-table-column>
                <el-table-column prop="purchase_date" label="日期" width="100" />
                <el-table-column prop="operator" label="经办人" width="90" />
              </el-table>
              <el-empty v-else description="暂无采购记录" :image-size="50" />

              <el-divider content-position="left">销售出库</el-divider>
              <el-table v-if="partDetail.sales?.length" :data="partDetail.sales" size="small" border>
                <el-table-column prop="customer_name" label="客户" min-width="110" />
                <el-table-column prop="quantity" label="数量" width="70" />
                <el-table-column prop="total" label="总额" width="100">
                  <template #default="{ row }">{{ Number(row.total || 0).toLocaleString() }}</template>
                </el-table-column>
                <el-table-column prop="sales_date" label="日期" width="100" />
                <el-table-column prop="operator" label="经办人" width="90" />
              </el-table>
              <el-empty v-else description="暂无销售记录" :image-size="50" />

              <div class="drawer-actions">
                <el-button v-if="user.hasPerm('spare:edit')" type="primary" @click="openPartEdit(partDetail)">
                  编辑
                </el-button>
                <el-button @click="partDetailVisible = false">关闭</el-button>
              </div>
            </template>
          </el-drawer>

          <!-- 备件新增/编辑 -->
          <el-dialog v-model="partFormVisible" :title="partForm.id ? '编辑备件' : '新增备件'" width="680px" top="5vh"
            destroy-on-close>
            <el-form ref="partFormRef" :model="partForm" :rules="partFormRules" label-width="100px">
              <el-row :gutter="12">
                <el-col :xs="24" :sm="12">
                  <el-form-item label="名称" prop="name">
                    <el-input v-model="partForm.name" placeholder="必填" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="编码">
                    <el-input v-model="partForm.code" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="分类">
                    <el-select v-model="partForm.category" allow-create filterable clearable class="w-full">
                      <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="单位">
                    <el-select v-model="partForm.unit" class="w-full">
                      <el-option v-for="u in ['个', '块', '条', '根', '套', '台', '盒', '瓶', '米']" :key="u"
                        :label="u" :value="u" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="品牌">
                    <el-input v-model="partForm.brand" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="型号">
                    <el-input v-model="partForm.model" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="规格">
                    <el-input v-model="partForm.specification" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="厂家">
                    <el-input v-model="partForm.manufacturer" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="序列号">
                    <el-input v-model="partForm.serial_number" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="安全库存">
                    <el-input-number v-model="partForm.min_stock" :min="0" class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="参考价">
                    <el-input-number v-model="partForm.reference_price" :min="0" :precision="2" class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24" :sm="12">
                  <el-form-item label="保修期(月)">
                    <el-input-number v-model="partForm.warranty_months" :min="0" class="w-full" />
                  </el-form-item>
                </el-col>
                <el-col :xs="24">
                  <el-form-item label="备注">
                    <el-input v-model="partForm.remark" type="textarea" :rows="2" />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
            <template #footer>
              <el-button @click="partFormVisible = false">取消</el-button>
              <el-button type="primary" :loading="saving" @click="savePart">保存</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>

        <!-- ==================== 库存 ==================== -->
        <el-tab-pane label="库存管理" name="stocks" lazy>
          <div class="tab-toolbar">
            <div class="filter-row">
              <el-input v-model="stockQuery.search" placeholder="搜索备件名称 / 编码" clearable class="filter-search"
                @keyup.enter="reload('stock')" @clear="reload('stock')" />
              <el-button type="primary" plain :icon="Search" @click="reload('stock')">查询</el-button>
            </div>
            <el-button v-if="user.hasPerm('spare:add')" type="primary" :icon="Plus" @click="openStockCreate">
              新增库存
            </el-button>
          </div>

          <DataTable ref="stockTableRef" :columns="stockColumns" :fetch-data="fetchSpareStocks"
            :query="stockQuery" row-key="id" />

          <el-dialog v-model="stockFormVisible" :title="stockForm.id ? '编辑库存' : '新增库存'" width="560px" top="5vh"
            destroy-on-close>
            <el-form ref="stockFormRef" :model="stockForm" :rules="stockFormRules" label-width="100px">
              <el-form-item label="备件" prop="spare_part_id">
                <el-select v-model="stockForm.spare_part_id" filterable class="w-full">
                  <el-option v-for="p in spareParts" :key="p.id" :label="p.name" :value="p.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="库位">
                <el-input v-model="stockForm.location" placeholder="默认库位" />
              </el-form-item>
              <el-form-item label="数量" prop="quantity">
                <el-input-number v-model="stockForm.quantity" :min="0" class="w-full" />
              </el-form-item>
              <el-form-item label="单价">
                <el-input-number v-model="stockForm.unit_price" :min="0" :precision="2" class="w-full" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="stockFormVisible = false">取消</el-button>
              <el-button type="primary" :loading="saving" @click="saveStock">保存</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>

        <!-- ==================== 采购 ==================== -->
        <el-tab-pane label="采购入库" name="purchases" lazy>
          <div class="tab-toolbar">
            <div class="filter-row">
              <el-input v-model="purchaseQuery.search" placeholder="搜索备件 / 供应商" clearable class="filter-search"
                @keyup.enter="reload('purchase')" @clear="reload('purchase')" />
              <el-button type="primary" plain :icon="Search" @click="reload('purchase')">查询</el-button>
            </div>
            <el-button v-if="user.hasPerm('spare:add')" type="primary" :icon="Plus" @click="openPurchaseCreate">
              采购入库
            </el-button>
          </div>

          <DataTable ref="purchaseTableRef" :columns="purchaseColumns" :fetch-data="fetchPurchaseOrders"
            :query="purchaseQuery" row-key="id" />

          <el-dialog v-model="purchaseFormVisible" title="采购入库" width="560px" top="5vh" destroy-on-close>
            <el-form ref="purchaseFormRef" :model="purchaseForm" :rules="purchaseFormRules" label-width="100px">
              <el-form-item label="备件" prop="spare_part_id">
                <el-select v-model="purchaseForm.spare_part_id" filterable class="w-full">
                  <el-option v-for="p in spareParts" :key="p.id" :label="p.name" :value="p.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="数量" prop="quantity">
                <el-input-number v-model="purchaseForm.quantity" :min="1" class="w-full" />
              </el-form-item>
              <el-form-item label="单价">
                <el-input-number v-model="purchaseForm.unit_price" :min="0" :precision="2" class="w-full" />
              </el-form-item>
              <el-form-item label="供应商">
                <el-input v-model="purchaseForm.supplier" />
              </el-form-item>
              <el-form-item label="采购日期">
                <el-date-picker v-model="purchaseForm.purchase_date" type="date" value-format="YYYY-MM-DD"
                  class="w-full" placeholder="默认今天" />
              </el-form-item>
              <el-form-item label="备注">
                <el-input v-model="purchaseForm.remark" type="textarea" :rows="2" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="purchaseFormVisible = false">取消</el-button>
              <el-button type="primary" :loading="saving" @click="savePurchase">入库</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>

        <!-- ==================== 销售 ==================== -->
        <el-tab-pane label="销售出库" name="sales" lazy>
          <div class="tab-toolbar">
            <div class="filter-row">
              <el-input v-model="salesQuery.search" placeholder="搜索备件名称" clearable class="filter-search"
                @keyup.enter="reload('sales')" @clear="reload('sales')" />
              <el-button type="primary" plain :icon="Search" @click="reload('sales')">查询</el-button>
            </div>
            <el-button v-if="user.hasPerm('spare:add')" type="primary" :icon="Plus" @click="openSalesCreate">
              销售出库
            </el-button>
          </div>

          <DataTable ref="salesTableRef" :columns="salesColumns" :fetch-data="fetchSalesOrders"
            :query="salesQuery" row-key="id" />

          <el-dialog v-model="salesFormVisible" title="销售出库" width="560px" top="5vh" destroy-on-close>
            <el-form ref="salesFormRef" :model="salesForm" :rules="salesFormRules" label-width="100px">
              <el-form-item label="备件" prop="spare_part_id">
                <el-select v-model="salesForm.spare_part_id" filterable class="w-full">
                  <el-option v-for="p in spareParts" :key="p.id" :label="p.name" :value="p.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="客户" prop="customer_id">
                <el-select v-model="salesForm.customer_id" filterable class="w-full">
                  <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="数量" prop="quantity">
                <el-input-number v-model="salesForm.quantity" :min="1" class="w-full" />
              </el-form-item>
              <el-form-item label="单价">
                <el-input-number v-model="salesForm.unit_price" :min="0" :precision="2" class="w-full" />
              </el-form-item>
              <el-form-item label="出库日期">
                <el-date-picker v-model="salesForm.sales_date" type="date" value-format="YYYY-MM-DD"
                  class="w-full" placeholder="默认今天" />
              </el-form-item>
              <el-form-item label="备注">
                <el-input v-model="salesForm.remark" type="textarea" :rows="2" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="salesFormVisible = false">取消</el-button>
              <el-button type="primary" :loading="saving" @click="saveSales">出库</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Plus, Search } from '@element-plus/icons-vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import {
  fetchSpareParts, fetchSparePart, createSparePart, updateSparePart, deleteSparePart,
  fetchSpareStocks, createSpareStock, updateSpareStock, deleteSpareStock,
  fetchPurchaseOrders, createPurchaseOrder, deletePurchaseOrder,
  fetchSalesOrders, createSalesOrder, deleteSalesOrder,
  fetchSpareDicts,
  type SparePart, type SpareStock, type PurchaseOrderItem, type SalesOrderItem, type SpareDicts,
} from '@/api/spare'

const user = useUserStore()
const ui = useUiStore()
const dicts = ref<SpareDicts | null>(null)
const spareParts = computed(() => dicts.value?.spare_parts || [])
const customers = computed(() => dicts.value?.customers || [])
const categories = computed(() => dicts.value?.categories || [])

const activeTab = ref('archive')
const partTableRef = ref()
const stockTableRef = ref()
const purchaseTableRef = ref()
const salesTableRef = ref()

// 侧栏入口（/app/spare-parts?tab=stocks 等）自动定位标签页
const route = useRoute()
watch(
  () => route.query.tab,
  (tab) => {
    if (tab && ['stocks', 'purchases', 'sales'].includes(String(tab))) {
      activeTab.value = String(tab)
    }
  },
  { immediate: true },
)

const partQuery = reactive<Record<string, unknown>>({ search: '', category: '' })
const stockQuery = reactive<Record<string, unknown>>({ search: '' })
const purchaseQuery = reactive<Record<string, unknown>>({ search: '' })
const salesQuery = reactive<Record<string, unknown>>({ search: '' })

function reload(kind: 'part' | 'stock' | 'purchase' | 'sales') {
  const refs = { part: partTableRef, stock: stockTableRef, purchase: purchaseTableRef, sales: salesTableRef }
  refs[kind].value?.refresh()
}

// ==================== 档案 ====================
const partColumns = computed<DataColumn[]>(() => [
  { key: 'name', label: '名称', minWidth: 160, asTitle: true },
  { key: 'code', label: '编码', width: 110 },
  { key: 'category', label: '分类', width: 90 },
  { key: 'brand', label: '品牌', width: 90 },
  { key: 'model', label: '型号', minWidth: 100 },
  { key: 'unit', label: '单位', width: 60 },
  { key: 'min_stock', label: '安全库存', width: 90 },
  { key: 'total_stock', label: '总库存', width: 90, cellClass: (r) => (r.stock_alert ? 'alert-stock' : '') },
  { key: 'stock_alert_label', label: '预警', width: 90, type: 'tag', asTag: true,
    tagMap: { 库存预警: 'danger', 正常: 'info' } },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'spare:edit', icon: 'Edit',
        onClick: (row) => openPartEdit(row as unknown as SparePart) },
      { label: '删除', type: 'danger', link: true, perm: 'spare:delete', icon: 'Delete',
        onClick: (row) => onPartDelete(row as unknown as SparePart) },
    ] },
])

const partDetailVisible = ref(false)
const partDetail = ref<SparePart | null>(null)

async function openPartDetail(row: Record<string, unknown>) {
  try {
    partDetail.value = await fetchSparePart(row.id as number)
    partDetailVisible.value = true
  } catch { /* toast */ }
}

interface PartFormModel {
  id?: number
  name: string
  code: string
  category: string
  brand: string
  model: string
  specification: string
  unit: string
  min_stock: number
  reference_price: number
  warranty_months: number
  manufacturer: string
  serial_number: string
  remark: string
}

const partFormVisible = ref(false)
const saving = ref(false)
const partFormRef = ref()
const partForm = reactive<PartFormModel>(blankPartForm())

function blankPartForm(): PartFormModel {
  return {
    id: undefined, name: '', code: '', category: '', brand: '', model: '', specification: '',
    unit: '个', min_stock: 0, reference_price: 0, warranty_months: 0,
    manufacturer: '', serial_number: '', remark: '',
  }
}

const partFormRules = { name: [{ required: true, message: '请输入备件名称', trigger: 'blur' }] }

function openPartCreate() {
  Object.assign(partForm, blankPartForm())
  partFormVisible.value = true
}

function openPartEdit(p: SparePart) {
  Object.assign(partForm, blankPartForm(), {
    id: p.id, name: p.name, code: p.code, category: p.category, brand: p.brand,
    model: p.model, specification: p.specification, unit: p.unit || '个',
    min_stock: p.min_stock, reference_price: p.reference_price,
    warranty_months: p.warranty_months, manufacturer: p.manufacturer,
    serial_number: p.serial_number, remark: p.remark,
  })
  partDetailVisible.value = false
  partFormVisible.value = true
}

async function savePart() {
  try { await partFormRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { ...partForm }
    if (partForm.id) {
      await updateSparePart(partForm.id, payload)
      ui.toast('备件已更新', 'success')
    } else {
      await createSparePart(payload)
      ui.toast('备件已创建', 'success')
    }
    partFormVisible.value = false
    reload('part')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onPartDelete(p: SparePart) {
  try {
    await ElMessageBox.confirm(`确定删除备件「${p.name}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteSparePart(p.id)
    ui.toast('已删除', 'success')
    partDetailVisible.value = false
    reload('part')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// ==================== 库存 ====================
const stockColumns = computed<DataColumn[]>(() => [
  { key: 'spare_part_name', label: '备件', minWidth: 180, asTitle: true },
  { key: 'location', label: '库位', minWidth: 110 },
  { key: 'quantity', label: '数量', width: 90 },
  { key: 'unit_price', label: '单价', width: 110, type: 'money' },
  { key: 'updated_at', label: '更新时间', width: 140 },
  { key: 'actions', label: '操作', width: 110, type: 'action', fixed: 'right',
    actions: [
      { label: '编辑', type: 'primary', link: true, perm: 'spare:edit', icon: 'Edit',
        onClick: (row) => openStockEdit(row as unknown as SpareStock) },
      { label: '删除', type: 'danger', link: true, perm: 'spare:delete', icon: 'Delete',
        onClick: (row) => onStockDelete(row as unknown as SpareStock) },
    ] },
])

interface StockFormModel {
  id?: number
  spare_part_id: number | null
  location: string
  quantity: number
  unit_price: number
}

const stockFormVisible = ref(false)
const stockFormRef = ref()
const stockForm = reactive<StockFormModel>(blankStockForm())

function blankStockForm(): StockFormModel {
  return { id: undefined, spare_part_id: null, location: '', quantity: 0, unit_price: 0 }
}

const stockFormRules = {
  spare_part_id: [{ required: true, message: '请选择备件', trigger: 'change' }],
}

function openStockCreate() {
  Object.assign(stockForm, blankStockForm())
  stockFormVisible.value = true
}

function openStockEdit(s: SpareStock) {
  Object.assign(stockForm, blankStockForm(), {
    id: s.id, spare_part_id: s.spare_part_id, location: s.location,
    quantity: s.quantity, unit_price: s.unit_price,
  })
  stockFormVisible.value = true
}

async function saveStock() {
  try { await stockFormRef.value?.validate() } catch { return }
  saving.value = true
  try {
    const payload = { ...stockForm }
    if (stockForm.id) {
      await updateSpareStock(stockForm.id, payload)
      ui.toast('库存已更新', 'success')
    } else {
      await createSpareStock(payload)
      ui.toast('库存已创建', 'success')
    }
    stockFormVisible.value = false
    reload('stock')
    reload('part')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onStockDelete(s: SpareStock) {
  try {
    await ElMessageBox.confirm(`确定删除「${s.spare_part_name}」在「${s.location || '默认库位'}」的库存记录吗？`,
      '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteSpareStock(s.id)
    ui.toast('已删除', 'success')
    reload('stock')
    reload('part')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// ==================== 采购 ====================
const purchaseColumns = computed<DataColumn[]>(() => [
  { key: 'spare_part_name', label: '备件', minWidth: 160, asTitle: true },
  { key: 'supplier_name', label: '供应商', minWidth: 120 },
  { key: 'quantity', label: '数量', width: 80 },
  { key: 'unit_price', label: '单价', width: 100, type: 'money' },
  { key: 'total', label: '总额', width: 110, type: 'money' },
  { key: 'purchase_date', label: '日期', width: 100, type: 'date' },
  { key: 'operator', label: '经办人', width: 90 },
  { key: 'actions', label: '操作', width: 90, type: 'action', fixed: 'right',
    actions: [
      { label: '删除', type: 'danger', link: true, perm: 'spare:delete', icon: 'Delete',
        onClick: (row) => onPurchaseDelete(row as unknown as PurchaseOrderItem) },
    ] },
])

interface PurchaseFormModel {
  spare_part_id: number | null
  quantity: number
  unit_price: number
  supplier: string
  purchase_date: string
  remark: string
}

const purchaseFormVisible = ref(false)
const purchaseFormRef = ref()
const purchaseForm = reactive<PurchaseFormModel>(blankPurchaseForm())

function blankPurchaseForm(): PurchaseFormModel {
  return { spare_part_id: null, quantity: 1, unit_price: 0, supplier: '', purchase_date: '', remark: '' }
}

const purchaseFormRules = {
  spare_part_id: [{ required: true, message: '请选择备件', trigger: 'change' }],
  quantity: [
    { required: true, message: '请输入数量', trigger: 'change' },
    { type: 'number', min: 1, message: '数量必须大于 0', trigger: 'change' },
  ],
}

function openPurchaseCreate() {
  Object.assign(purchaseForm, blankPurchaseForm())
  purchaseFormVisible.value = true
}

async function savePurchase() {
  try { await purchaseFormRef.value?.validate() } catch { return }
  if (!purchaseForm.quantity || purchaseForm.quantity <= 0) {
    ui.toast('数量必须大于 0', 'warning')
    return
  }
  saving.value = true
  try {
    await createPurchaseOrder({ ...purchaseForm })
    ui.toast('采购入库成功', 'success')
    purchaseFormVisible.value = false
    reload('purchase')
    reload('part')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onPurchaseDelete(po: PurchaseOrderItem) {
  try {
    await ElMessageBox.confirm(`确定删除采购单（${po.spare_part_name} × ${po.quantity}）吗？删除将冲销库存。`,
      '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deletePurchaseOrder(po.id)
    ui.toast('已删除', 'success')
    reload('purchase')
    reload('part')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// ==================== 销售 ====================
const salesColumns = computed<DataColumn[]>(() => [
  { key: 'spare_part_name', label: '备件', minWidth: 150, asTitle: true },
  { key: 'customer_name', label: '客户', minWidth: 130 },
  { key: 'quantity', label: '数量', width: 80 },
  { key: 'unit_price', label: '单价', width: 100, type: 'money' },
  { key: 'total', label: '总额', width: 110, type: 'money' },
  { key: 'sales_date', label: '日期', width: 100, type: 'date' },
  { key: 'operator', label: '经办人', width: 90 },
  { key: 'actions', label: '操作', width: 90, type: 'action', fixed: 'right',
    actions: [
      { label: '删除', type: 'danger', link: true, perm: 'spare:delete', icon: 'Delete',
        onClick: (row) => onSalesDelete(row as unknown as SalesOrderItem) },
    ] },
])

interface SalesFormModel {
  spare_part_id: number | null
  customer_id: number | null
  quantity: number
  unit_price: number
  sales_date: string
  remark: string
}

const salesFormVisible = ref(false)
const salesFormRef = ref()
const salesForm = reactive<SalesFormModel>(blankSalesForm())

function blankSalesForm(): SalesFormModel {
  return { spare_part_id: null, customer_id: null, quantity: 1, unit_price: 0, sales_date: '', remark: '' }
}

const salesFormRules = {
  spare_part_id: [{ required: true, message: '请选择备件', trigger: 'change' }],
  customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
}

function openSalesCreate() {
  Object.assign(salesForm, blankSalesForm())
  salesFormVisible.value = true
}

async function saveSales() {
  try { await salesFormRef.value?.validate() } catch { return }
  if (!salesForm.quantity || salesForm.quantity <= 0) {
    ui.toast('数量必须大于 0', 'warning')
    return
  }
  saving.value = true
  try {
    await createSalesOrder({ ...salesForm })
    ui.toast('销售出库成功', 'success')
    salesFormVisible.value = false
    reload('sales')
    reload('part')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onSalesDelete(so: SalesOrderItem) {
  try {
    await ElMessageBox.confirm(`确定删除销售单（${so.spare_part_name} × ${so.quantity}）吗？删除将回补库存。`,
      '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteSalesOrder(so.id)
    ui.toast('已删除', 'success')
    reload('sales')
    reload('part')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

onMounted(() => {
  fetchSpareDicts().then((d) => (dicts.value = d))
})
</script>

<style scoped>
.tabs-card { border-radius: 10px; }
.module-tabs { padding: 0 4px; }
.tab-toolbar { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-search { width: 220px; max-width: 100%; }
.filter-item { width: 130px; max-width: 100%; }
.w-full { width: 100%; }
.drawer-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.alert-stock { color: var(--el-color-danger); font-weight: 600; }
</style>
