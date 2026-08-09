<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">设备管理</h2>
      <div class="header-actions">
        <el-button :icon="Download" plain @click="exportVisible = true">导出</el-button>
        <el-button :icon="Document" plain @click="loadMyRequests">我的导出申请</el-button>
        <el-button v-if="user.hasPerm('device:add')" :icon="Upload" plain @click="importVisible = true">导入</el-button>
        <el-button v-if="user.hasPerm('device:add')" type="primary" :icon="Plus" @click="openCreate">
          新增设备
        </el-button>
      </div>
    </div>

    <!-- 导出对话框（三类预设 + 列选择 + 密码审核流） -->
    <ExportDialog v-model="exportVisible" module="device" title="导出设备"
      @submit="onExportSubmit" />

    <!-- 我的导出申请 -->
    <el-dialog v-model="requestsVisible" title="我的导出申请" width="760px" top="6vh" destroy-on-close>
      <el-table v-if="exportRequests.length" :data="exportRequests" size="small" border>
        <el-table-column prop="created_at" label="申请时间" width="140" />
        <el-table-column prop="reason" label="申请原因" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status_label" label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="requestStatusTag(row.status)">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="review_comment" label="审核意见" min-width="150" show-overflow-tooltip />
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button v-if="row.status === 'approved' && !row.downloaded" size="small" link
              type="primary" @click="downloadPasswordExport(row.file_token)">下载</el-button>
            <span v-else-if="row.downloaded" class="muted">已下载</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无导出申请" :image-size="60" />
    </el-dialog>

    <!-- 导入弹窗 -->
    <el-dialog v-model="importVisible" title="批量导入设备" width="520px" destroy-on-close>
      <el-alert type="info" :closable="false" class="mb-2" show-icon
        title="请先下载导入模板（Excel），按列填写后上传；客户名须已存在，导入后自动刷新客户设备数" />
      <div class="mb-2">
        <el-button size="small" link type="primary" @click="downloadTemplate">下载导入模板</el-button>
      </div>
      <el-upload ref="importUploadRef" drag :auto-upload="false" :limit="1" accept=".xlsx,.xls"
        :on-change="onImportFileChange" :on-remove="() => importFile = null">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽或点击选择 Excel 文件</div>
      </el-upload>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="doImport">开始导入</el-button>
      </template>
    </el-dialog>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-input
          v-model="query.search"
          placeholder="搜索名称 / IP / 品牌"
          clearable
          class="filter-search"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-select v-model="query.brand" placeholder="品牌" clearable class="filter-item" @change="reload">
          <el-option v-for="b in brands" :key="b" :label="b" :value="b" />
        </el-select>
        <el-select v-model="query.device_type" placeholder="类型" clearable class="filter-item" @change="reload">
          <el-option v-for="t in deviceTypes" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>
        <el-select v-if="mode === 'table'" v-model="query.customer_id" placeholder="客户" clearable filterable
          class="filter-item" @change="onCustomerFilterChange">
          <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-button type="primary" plain :icon="Search" @click="reload">查询</el-button>
        <template v-if="mode === 'table'">
          <el-button size="small" text type="primary" :icon="Setting" @click="openColSettings">
            列设置
          </el-button>
          <el-tag type="primary" effect="plain" class="scope-tag">
            客户：{{ tableCustomer?.name || '全部客户' }} · 共 {{ tableTotal }} 台
          </el-tag>
          <el-button size="small" text type="primary" :icon="Back" @click="backToTree">返回</el-button>
        </template>
      </div>
    </el-card>

    <!-- 树模式：按地区折叠（市 → 客户），点击客户进入表格模式 -->
    <el-card v-if="mode === 'tree'" shadow="never" v-loading="treeLoading">
      <GroupTree
        :nodes="tree"
        :leaf-depth="1"
        badge-key="device_count"
        :default-expanded="hasFilter ? 1 : 0"
        @leaf-click="enterTable"
      >
        <template #leaf="{ node }">
          <div class="tree-block cust-leaf" @click="enterTable(node)">
            <el-icon color="#2563eb"><OfficeBuilding /></el-icon>
            <span class="tree-name">{{ node.name }}</span>
            <el-tag size="small" type="info">设备 {{ node.device_count ?? 0 }}</el-tag>
            <span class="row-actions" @click.stop>
              <el-button size="small" link type="primary" @click="enterTable(node)">查看设备</el-button>
            </span>
          </div>
        </template>
      </GroupTree>
      <el-empty v-if="!treeLoading && !tree.length" description="暂无设备" :image-size="60" />
    </el-card>

    <!-- 表格模式：当前客户完整设备表格 -->
    <template v-else>
      <DataTable
        ref="tableRef"
        :columns="columns"
        :fetch-data="fetchDevices"
        :query="query"
        row-key="id"
        :column-settings="{ storageKey: 'device-table-columns' }"
        @row-click="openDetail"
      />
    </template>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detail?.device_name || '设备详情'" width="680px">
      <el-descriptions v-if="detail" :column="2" border size="small">
        <el-descriptions-item label="客户">{{ detail.customer_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ detail.device_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="网络类型">{{ detail.network_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="品牌">{{ detail.brand || '-' }}</el-descriptions-item>
        <el-descriptions-item label="型号">{{ detail.model || '-' }}</el-descriptions-item>
        <el-descriptions-item label="序列号">{{ detail.serial_number || '-' }}</el-descriptions-item>
        <el-descriptions-item label="IP:端口">
          <code>{{ detail.ip_address }}:{{ detail.port }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="登录">
          {{ detail.username || '-' }} / {{ detail.login_method || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="系统版本">{{ detail.os_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="规则库版本">{{ detail.rule_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="安装位置">{{ detail.location || '-' }}</el-descriptions-item>
        <el-descriptions-item label="机柜">
          <template v-if="detail.rack_name">{{ detail.rack_location || '-' }} / {{ detail.rack_name }}<span v-if="detail.rack_slot"> / {{ detail.rack_slot }}</span></template>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="建设时间">{{ detail.build_date || '-' }}</el-descriptions-item>
        <el-descriptions-item label="授权">
          {{ detail.license_expiry || '-' }}
          <el-tag v-if="detail.license_remaining_days != null" size="small"
            :type="detail.license_remaining_days < 0 ? 'danger' : 'warning'" class="ml-1">
            {{ detail.license_remaining_days < 0 ? `过期 ${-detail.license_remaining_days} 天` : `剩 ${detail.license_remaining_days} 天` }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="证书到期">
          {{ detail.cert_expiry_date || '-' }}
          <el-tag v-if="detail.cert_expiry_date && detail.cert_expiry_date < todayStr" size="small" type="danger" class="ml-1">已过期</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="在用">
          <el-tag size="small" :type="detail.is_in_use ? 'success' : 'info'">
            {{ detail.is_in_use ? '在用' : '停用' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
      </el-descriptions>

      <!-- 配置备份（含巡检上传同步记录） -->
      <el-divider content-position="left">配置备份</el-divider>
      <div class="backup-toolbar">
        <el-checkbox-group v-model="compareSel" size="small" class="backup-compare-sel">
          <el-checkbox v-for="b in backups.slice(0, 20)" :key="b.id" :value="b.id" size="small">
            #{{ b.id }}
          </el-checkbox>
        </el-checkbox-group>
        <el-button size="small" :disabled="compareSel.length !== 2" @click="doCompare">对比</el-button>
        <el-button v-if="user.hasPerm('device:edit')" size="small" type="primary" plain @click="openBackupAdd">
          新增备份
        </el-button>
      </div>
      <div v-loading="backupsLoading" class="backup-list">
        <el-table v-if="backups.length" :data="backups" size="small" border stripe max-height="220">
          <el-table-column prop="backup_type" label="类型" width="100" />
          <el-table-column prop="backup_method" label="来源" width="100" />
          <el-table-column prop="backup_date" label="日期" width="100" />
          <el-table-column prop="created_by" label="创建人" min-width="90" />
          <el-table-column label="操作" width="220">
            <template #default="{ row }">
              <el-button v-if="row.has_content" size="small" link type="primary" @click="viewBackup(row)">查看</el-button>
              <el-button v-if="row.has_file" size="small" link type="primary" @click="downloadBackup(row)">下载</el-button>
              <el-button v-if="user.hasPerm('device:edit') && row.has_content" size="small" link type="warning"
                @click="onRollback(row)">回滚</el-button>
              <el-button v-if="user.hasPerm('device:delete')" size="small" link type="danger"
                @click="onBackupDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!backupsLoading" description="暂无配置备份（巡检提交资料将自动同步）" :image-size="50" />
      </div>

      <!-- 新增备份弹窗 -->
      <el-dialog v-model="backupAddVisible" title="新增配置备份" width="560px" destroy-on-close>
        <el-form label-width="80px">
          <el-form-item label="类型">
            <el-select v-model="backupForm.type" class="w-full">
              <el-option v-for="t in ['运行配置', '启动配置', '其他']" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="内容">
            <el-input v-model="backupForm.content" type="textarea" :rows="8" placeholder="粘贴配置内容（与文件二选一）" />
          </el-form-item>
          <el-form-item label="文件">
            <el-upload ref="backupUploadRef" :auto-upload="false" :limit="1" accept=".txt,.cfg,.conf,.log"
              :on-change="onBackupFileChange" :on-remove="() => backupForm.file = null">
              <el-button size="small" plain :icon="Upload">选择文件（可选）</el-button>
            </el-upload>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="backupAddVisible = false">取消</el-button>
          <el-button type="primary" :loading="backupSaving" @click="saveBackup">保存</el-button>
        </template>
      </el-dialog>

      <!-- 对比弹窗 -->
      <el-dialog v-model="diffVisible" title="配置对比" width="900px" top="4vh" destroy-on-close>
        <div v-loading="diffLoading" class="diff-wrap">
          <div v-if="diffLines.length" class="diff-table">
            <div v-for="(line, i) in diffLines" :key="i" :class="['diff-row', `diff-${line.tag}`]">
              <span class="diff-a">{{ line.line_a || ' ' }}</span>
              <span class="diff-b">{{ line.line_b || ' ' }}</span>
            </div>
          </div>
          <el-empty v-else-if="!diffLoading" description="两版本内容一致" :image-size="50" />
        </div>
      </el-dialog>

      <!-- 关联工单 / 巡检记录（反向视图） -->
      <el-divider content-position="left">关联工单与巡检</el-divider>
      <div v-loading="relatedLoading" class="related-list">
        <template v-if="relatedTickets.length || relatedInspections.length">
          <el-table :data="relatedTickets" size="small" border stripe max-height="200">
            <el-table-column label="关联工单" min-width="200">
              <template #default="{ row }">
                <router-link :to="toRouterPath(`/app/tickets/${row.id}`)" class="row-link">
                  {{ row.number }} · {{ row.title }}
                </router-link>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column prop="created_at" label="创建时间" width="100" />
          </el-table>
          <el-table :data="relatedInspections" size="small" border stripe max-height="200" class="mt-2">
            <el-table-column label="巡检记录" min-width="200">
              <template #default="{ row }">
                <router-link :to="toRouterPath(`/app/inspections/${row.id}`)" class="row-link">
                  {{ row.title }}<span v-if="row.task_title" class="text-muted">（{{ row.task_title }}）</span>
                </router-link>
              </template>
            </el-table-column>
            <el-table-column prop="overall_status" label="总体" width="80" />
            <el-table-column prop="review_status" label="审核" width="90" />
            <el-table-column prop="inspection_date" label="巡检日期" width="100" />
          </el-table>
        </template>
        <el-empty v-else-if="!relatedLoading" description="暂无关联工单/巡检" :image-size="40" />
      </div>

      <template #footer>
        <el-button v-if="user.hasPerm('device:reveal') && detail?.has_password" @click="revealPwd">
          <el-icon class="mr-1"><View /></el-icon>{{ pwdVisible ? '隐藏密码' : '查看密码' }}
        </el-button>
        <el-button v-if="user.hasPerm('device:reveal')" @click="openPwdHistory">
          历史密码
        </el-button>
        <el-button v-if="user.hasPerm('device:edit')" type="primary" @click="openEdit(detail!)">编辑</el-button>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 历史密码弹窗 -->
    <el-dialog v-model="pwdHistoryVisible" title="历史密码（查看明文将记录审计）" width="560px" destroy-on-close>
      <el-table v-loading="pwdHistoryLoading" :data="pwdHistory" size="small" border stripe max-height="360">
        <el-table-column prop="id" label="#" width="60" />
        <el-table-column prop="changed_by" label="修改人" width="120" />
        <el-table-column prop="created_at" label="时间" width="150" />
        <el-table-column prop="remark" label="备注" min-width="100" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="revealHistory(row.id)">查看明文</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!pwdHistoryLoading && !pwdHistory.length" description="暂无历史记录" :image-size="50" />
    </el-dialog>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="formVisible"
      :title="form.id ? '编辑设备' : '新增设备'"
      width="720px"
      top="4vh"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="110px" size="default">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12">
            <el-form-item label="设备名称" prop="device_name">
              <el-input v-model="form.device_name" placeholder="必填" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="所属客户">
              <el-select v-model="form.customer_id" filterable clearable class="w-full">
                <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="设备类型">
              <el-select v-model="form.device_type" filterable allow-create clearable class="w-full">
                <el-option v-for="t in deviceTypes" :key="t.name" :label="t.name" :value="t.name" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="网络类型">
              <el-select v-model="form.network_type" filterable allow-create clearable class="w-full">
                <el-option label="内网" value="内网" />
                <el-option label="外网" value="外网" />
                <el-option label="DMZ" value="DMZ" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="品牌/型号">
              <div class="flex-gap">
                <el-input v-model="form.brand" placeholder="品牌" />
                <el-input v-model="form.model" placeholder="型号" />
              </div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="IP地址">
              <el-input v-model="form.ip_address" placeholder="如 192.168.1.1" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="端口">
              <el-input-number v-model="form.port" :min="1" :max="65535" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="序列号">
              <el-input v-model="form.serial_number" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="登录方式">
              <el-select v-model="form.login_method" allow-create clearable class="w-full">
                <el-option label="SSH" value="SSH" />
                <el-option label="Telnet" value="Telnet" />
                <el-option label="Web" value="Web" />
                <el-option label="SNMP" value="SNMP" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="用户名">
              <el-input v-model="form.username" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item :label="form.id ? '新密码' : '密码'">
              <el-input v-model="form.password" type="password" show-password
                :placeholder="form.id ? '留空则不修改' : ''" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="安装位置">
              <el-input v-model="form.location" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="接口">
              <el-select v-model="form.interface" multiple filterable allow-create default-first-option
                class="w-full" placeholder="如 GigabitEthernet0/0/1" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="系统版本">
              <el-input v-model="form.os_version" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="规则库版本">
              <el-input v-model="form.rule_version" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="建设时间">
              <el-date-picker v-model="form.build_date" type="date" value-format="YYYY-MM-DD"
                class="w-full" placeholder="建设日期" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="授权开始">
              <el-date-picker v-model="form.license_start" type="date" value-format="YYYY-MM-DD"
                class="w-full" placeholder="开始日期" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="授权截止">
              <el-date-picker v-model="form.license_expiry" type="date" value-format="YYYY-MM-DD"
                class="w-full" placeholder="截止日期" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="证书到期">
              <el-date-picker v-model="form.cert_expiry_date" type="date" value-format="YYYY-MM-DD"
                class="w-full" placeholder="证书到期日" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
          <el-col :xs="24">
            <el-form-item label="状态">
              <el-checkbox v-model="form.is_in_use">在用</el-checkbox>
              <el-checkbox v-model="form.is_maintenance">有过维修</el-checkbox>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import type { UploadFile } from 'element-plus/es/components/upload'
import { ref, reactive, computed, onMounted } from 'vue'
import { Plus, Search, View, Download, Upload, UploadFilled, OfficeBuilding, Back, Setting, Document } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import GroupTree from '@/components/GroupTree.vue'
import DataTable, { type DataColumn } from '@/components/DataTable.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { IN_USE_LABELS } from '@/utils/labels'
import { toRouterPath } from '@/utils/sidebarNav'
import {
  fetchDevices, fetchDevice, createDevice, updateDevice, deleteDevice, revealPassword,
  fetchDeviceConfigBackups, fetchDeviceConfigBackupContent, deviceConfigBackupDownloadUrl,
  fetchDeviceRelated, exportDevices, importDevices, createConfigBackup, deleteConfigBackup,
  rollbackConfigBackup, fetchConfigBackupDiff, fetchPasswordHistory, type DiffLine,
  fetchDeviceTree, type Device, type DeviceForm, type DeviceConfigBackup,
  type DeviceTreeGroup, type RelatedTicket, type RelatedInspection,
  type PasswordHistoryItem, type DeviceExportRequestItem,
  requestDeviceExport, fetchDeviceExportRequests, exportPasswordDownloadUrl,
} from '@/api/devices'
import ExportDialog from '@/components/ExportDialog.vue'
import { handleExportResult } from '@/utils/export'

const route = useRoute()
const user = useUserStore()
const ui = useUiStore()

// 筛选 + 字典数据
const query = reactive<Record<string, unknown>>({ search: '', brand: '', device_type: '', customer_id: undefined })
const brands = ref<string[]>([])
const deviceTypes = ref<{ name: string }[]>([])
const customers = ref<{ id: number; name: string }[]>([])

// ==================== 双模式：树（市→客户） / 表格（完整字段） ====================
const mode = ref<'tree' | 'table'>('tree')
const tableCustomer = ref<{ id: number | null; name: string } | null>(null)
const tableTotal = ref(0)
const tableRef = ref()

function enterTable(node: Record<string, unknown>) {
  const id = node.id as number | null ?? null
  tableCustomer.value = { id, name: node.name as string || (id == null ? '未关联客户' : '') }
  query.customer_id = id ?? undefined
  mode.value = 'table'
  tableTotal.value = Number(node.device_count) || 0
  // DataTable 首次挂载后刷新
  setTimeout(() => tableRef.value?.refresh(), 0)
}

function backToTree() {
  mode.value = 'tree'
  query.customer_id = undefined
  tableCustomer.value = null
  loadTree()
}

function openColSettings() {
  tableRef.value?.openColumnSettings?.()
}

function onCustomerFilterChange() {
  const cid = query.customer_id as number | undefined
  tableCustomer.value = cid
    ? { id: cid, name: customers.value.find((c) => c.id === cid)?.name || `客户 #${cid}` }
    : { id: null, name: '全部客户' }
  tableRef.value?.refresh()
}

const columns = computed<DataColumn[]>(() => {
  // 与导出（vue_export.DEVICE_EXPORT_COLUMNS）字段全集对齐：全量进「列设置」，
  // defaultVisible:false 的列默认隐藏（机柜位置/建设时间/授权开始/网络类型/证书到期/改密记录），可按需开启。
  // 说明：登录密码为敏感信息，明文不下发列表（查看走详情弹窗 device:reveal + 审计、导出走审核流）。
  const cols: DataColumn[] = [
    { key: 'device_name', label: '设备名称', type: 'link', minWidth: 160, asTitle: true,
      link: (r) => `/app/devices/${r.id}` },
    { key: 'device_type', label: '类型', width: 90 },
    { key: 'customer_name', label: '客户', minWidth: 100 },
    { key: 'rack_location', label: '机房位置', minWidth: 100, cellClass: () => 'cell-muted' },
    { key: 'rack_name', label: '机柜号', minWidth: 90, cellClass: () => 'cell-muted' },
    { key: 'rack_slot', label: '机柜位置', width: 80, defaultVisible: false, cellClass: () => 'cell-muted' },
    { key: 'brand', label: '品牌', minWidth: 100,
      cellClass: () => 'cell-muted' },
    { key: 'model', label: '型号', minWidth: 120,
      cellClass: () => 'cell-muted' },
    { key: 'serial_number', label: '序列号', minWidth: 130,
      cellClass: () => 'cell-muted' },
    { key: 'network_type', label: '网络类型', width: 90, defaultVisible: false },
    { key: 'ip_address', label: 'IP地址', minWidth: 130 },
    { key: 'port', label: '端口', width: 70, cellClass: () => 'cell-muted' },
    { key: 'login_method', label: '登录方式', width: 90 },
    { key: 'username', label: '登录用户名', minWidth: 100, cellClass: () => 'cell-muted' },
    { key: 'location', label: '安装位置', minWidth: 120,
      cellClass: () => 'cell-muted' },
    { key: 'os_version', label: '系统版本', minWidth: 110 },
    { key: 'rule_version', label: '规则库版本', minWidth: 110 },
    { key: 'build_date', label: '建设时间', minWidth: 100, defaultVisible: false,
      cellClass: () => 'cell-muted' },
    { key: 'license_start', label: '授权开始', minWidth: 100, defaultVisible: false,
      cellClass: () => 'cell-muted' },
    { key: 'license_expiry', label: '授权截止', minWidth: 100,
      cellClass: () => 'cell-muted' },
    { key: 'cert_expiry_date', label: '证书到期', minWidth: 100, defaultVisible: false,
      cellClass: (r) => {
        const s = r.cert_expiry_date as string | undefined
        if (s && s < new Date().toISOString().slice(0, 10)) return 'cell-danger'
        return ''
      } },
    { key: 'license_remaining_days', label: '授权剩余', minWidth: 100,
      cellClass: (r) => {
        const d = r.license_remaining_days as number | null
        if (d != null && d < 0) return 'cell-danger'
        if (d != null && d <= 30) return 'cell-warn'
        return ''
      } },
    { key: 'is_maintenance', label: '是否维修', width: 90, valueMap: { 'true': '是', 'false': '否' },
      cellClass: () => 'cell-muted' },
    { key: 'is_in_use', label: '状态', width: 80, type: 'tag', asTag: true,
      tagMap: { 'true': 'success', 'false': 'info' }, valueMap: IN_USE_LABELS },
    { key: 'pwd_changed_by', label: '上次改密账号', minWidth: 110, defaultVisible: false,
      cellClass: () => 'cell-muted' },
    { key: 'pwd_changed_at', label: '上次改密时间', minWidth: 100, defaultVisible: false,
      cellClass: () => 'cell-muted' },
    { key: 'remark', label: '备注', minWidth: 140, cellClass: () => 'cell-muted' },
    { key: 'actions', label: '操作', width: 120, type: 'action', fixed: 'right',
      actions: [
        { label: '编辑', type: 'primary', link: true, perm: 'device:edit', icon: 'Edit',
          onClick: (row) => openEdit(row as unknown as Device) },
        { label: '删除', type: 'danger', link: true, perm: 'device:delete', icon: 'Delete',
          onClick: (row) => onDelete(row as unknown as Device) },
      ] },
  ]
  // 锁定单个客户时范围条已显示客户名，隐藏「客户」列避免重复
  if (query.customer_id) {
    return cols.filter((c) => c.key !== 'customer_name')
  }
  return cols
})

// ==================== 地区折叠树（市 → 客户） ====================
const tree = ref<DeviceTreeGroup[]>([])
const treeLoading = ref(false)
const hasFilter = computed(() =>
  Boolean(query.search || query.brand || query.device_type))

async function loadTree() {
  treeLoading.value = true
  try {
    const res = await fetchDeviceTree({
      search: query.search as string || undefined,
      brand: query.brand as string || undefined,
      device_type: query.device_type as string || undefined,
    })
    tree.value = res.tree
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    treeLoading.value = false
  }
}

// ==================== 导入 / 导出 ====================
const importVisible = ref(false)
const importing = ref(false)
const importUploadRef = ref()
const importFile = ref<File | null>(null)

function onImportFileChange(f: UploadFile) {
  importFile.value = f.raw ?? null
}

function downloadTemplate() {
  window.open('/exports/download-template/device', '_blank')
}

// ---- V24 导出筛选：列选择 + 三预设 + 密码审核流 ----
const exportVisible = ref(false)
const requestsVisible = ref(false)
const exportRequests = ref<DeviceExportRequestItem[]>([])

async function onExportSubmit(payload: Record<string, unknown>) {
  try {
    if (payload.has_password) {
      const filters = {
        preset: payload.preset,
        columns: payload.columns,
        customer_id: firstCustomerId(payload),
        search: query.search as string || undefined,
      }
      await requestDeviceExport(filters, payload.reason as string || '')
      ui.toast('申请已提交，请等待管理员审核（通知将在通过后推送）', 'success')
      exportVisible.value = false
      return
    }
    const res = await exportDevices({
      preset: payload.preset as string | undefined,
      columns: payload.columns as string[] | undefined,
      customer_id: firstCustomerId(payload),
      search: query.search as string || undefined,
    })
    handleExportResult(res, { close: () => { exportVisible.value = false } })
    ui.toast('导出成功', 'success')
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function loadMyRequests() {
  requestsVisible.value = true
  try {
    const d = await fetchDeviceExportRequests('mine')
    exportRequests.value = d.items
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function requestStatusTag(status: string): 'warning' | 'success' | 'danger' | 'info' {
  const map: Record<string, 'warning' | 'success' | 'danger' | 'info'> = {
    pending: 'warning', approved: 'success', rejected: 'danger',
  }
  return map[status] || 'info'
}

function firstCustomerId(payload: Record<string, unknown>): number | undefined {
  const ids = payload.customer_ids as number[] | undefined
  return ids?.length ? ids[0] : undefined
}

async function downloadPasswordExport(token: string) {
  try {
    const resp = await fetch(exportPasswordDownloadUrl(token), { credentials: 'include' })
    if (!resp.ok) {
      const j = await resp.json().catch(() => null)
      ui.toast(j?.message || '下载失败', 'error')
      return
    }
    const pwd = resp.headers.get('X-Export-Password') || ''
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = '设备密码表.xlsx'
    a.click()
    URL.revokeObjectURL(url)
    if (pwd) {
      await ElMessageBox.alert(`本次导出密码：${pwd}\n\n请妥善保存，用于解压加密包`, '加密包密码',
        { confirmButtonText: '我知道了' })
    }
    loadMyRequests()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function doImport() {
  if (!importFile.value) {
    ui.toast('请选择 Excel 文件', 'warning')
    return
  }
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('import_file', importFile.value)
    const res = await importDevices(fd)
    const msg = `导入完成：成功 ${res.created} 条${res.total_errors ? `，失败 ${res.total_errors} 条` : ''}`
    ui.toast(msg, res.total_errors ? 'warning' : 'success')
    if (res.errors.length) {
      ElMessageBox.alert(res.errors.join('\n'), '导入错误明细', {
        customStyle: { maxHeight: '70vh', overflow: 'auto', whiteSpace: 'pre-wrap' },
      }).catch(() => {})
    }
    importVisible.value = false
    loadTree()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    importing.value = false
  }
}

// 详情
const detailVisible = ref(false)
const detail = ref<Device | null>(null)
const pwdVisible = ref(false)
/** 今日 YYYY-MM-DD（证书到期比较） */
const todayStr = new Date().toISOString().slice(0, 10)
const backups = ref<DeviceConfigBackup[]>([])
const backupsLoading = ref(false)
const relatedTickets = ref<RelatedTicket[]>([])
const relatedInspections = ref<RelatedInspection[]>([])
const relatedLoading = ref(false)

async function openDetail(row: Record<string, unknown>) {
  const id = row.id as number
  try {
    detail.value = await fetchDevice(id)
    pwdVisible.value = false
    detailVisible.value = true
    loadBackups(id)
    loadRelated(id)
  } catch { /* toast */ }
}

async function loadRelated(deviceId: number) {
  relatedLoading.value = true
  try {
    const data = await fetchDeviceRelated(deviceId)
    relatedTickets.value = data.tickets
    relatedInspections.value = data.inspections
  } catch {
    relatedTickets.value = []
    relatedInspections.value = []
  } finally {
    relatedLoading.value = false
  }
}

async function loadBackups(deviceId: number) {
  backupsLoading.value = true
  try {
    backups.value = await fetchDeviceConfigBackups(deviceId)
  } catch { backups.value = [] } finally {
    backupsLoading.value = false
  }
}

function viewBackup(row: DeviceConfigBackup) {
  fetchDeviceConfigBackupContent(row.id)
    .then((r) => {
      ElMessageBox.alert(r.content || '（空）', `配置备份 · ${row.backup_type}`, {
        customStyle: { maxHeight: '70vh', overflow: 'auto' },
        confirmButtonText: '关闭',
      }).catch(() => {})
    })
    .catch(() => { /* toast */ })
}

function downloadBackup(row: DeviceConfigBackup) {
  window.open(deviceConfigBackupDownloadUrl(row.id), '_blank')
}

// ==================== 配置备份写操作（新增/对比/回滚/删除） ====================
const compareSel = ref<number[]>([])
const backupAddVisible = ref(false)
const backupSaving = ref(false)
const backupUploadRef = ref()
const backupForm = reactive<{ type: string; content: string; file: File | null }>({
  type: '运行配置', content: '', file: null,
})
const diffVisible = ref(false)
const diffLoading = ref(false)
const diffLines = ref<DiffLine[]>([])

function openBackupAdd() {
  backupForm.type = '运行配置'
  backupForm.content = ''
  backupForm.file = null
  backupUploadRef.value?.clearFiles?.()
  backupAddVisible.value = true
}

function onBackupFileChange(f: UploadFile) {
  backupForm.file = f.raw ?? null
}

async function saveBackup() {
  if (!detail.value) return
  if (!backupForm.content.trim() && !backupForm.file) {
    ui.toast('请填写配置内容或上传文件', 'warning')
    return
  }
  backupSaving.value = true
  try {
    const fd = new FormData()
    fd.append('config_content', backupForm.content)
    fd.append('backup_type', backupForm.type)
    if (backupForm.file) fd.append('config_file', backupForm.file)
    await createConfigBackup(detail.value.id, fd)
    ui.toast('配置备份已保存', 'success')
    backupAddVisible.value = false
    loadBackups(detail.value.id)
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    backupSaving.value = false
  }
}

async function doCompare() {
  if (compareSel.value.length !== 2) return
  diffLoading.value = true
  diffVisible.value = true
  try {
    const [a, b] = compareSel.value
    const res = await fetchConfigBackupDiff(a, b)
    diffLines.value = res.lines
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    diffLoading.value = false
  }
}

async function onRollback(row: DeviceConfigBackup) {
  try {
    await ElMessageBox.confirm(
      `确定回滚到版本 #${row.id} 吗？将生成一条新的备份记录（原版本保留）`, '回滚确认', { type: 'warning' })
  } catch { return }
  try {
    await rollbackConfigBackup(row.id)
    ui.toast('已生成回滚备份', 'success')
    if (detail.value) loadBackups(detail.value.id)
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function onBackupDelete(row: DeviceConfigBackup) {
  try {
    await ElMessageBox.confirm(`确定删除备份 #${row.id}（${row.backup_method}）吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deleteConfigBackup(row.id)
    ui.toast('已删除', 'success')
    if (detail.value) loadBackups(detail.value.id)
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

async function revealPwd() {
  if (!detail.value) return
  if (!pwdVisible.value) {
    const res = await revealPassword(detail.value.id)
    detail.value = { ...detail.value, password: res.password }
    pwdVisible.value = true
  } else {
    pwdVisible.value = false
  }
}

// 历史密码
const pwdHistoryVisible = ref(false)
const pwdHistoryLoading = ref(false)
const pwdHistory = ref<PasswordHistoryItem[]>([])

async function openPwdHistory() {
  if (!detail.value) return
  pwdHistoryVisible.value = true
  pwdHistoryLoading.value = true
  try {
    pwdHistory.value = await fetchPasswordHistory(detail.value.id)
  } catch {
    pwdHistory.value = []
  } finally {
    pwdHistoryLoading.value = false
  }
}

async function revealHistory(historyId: number) {
  if (!detail.value) return
  try {
    const res = await revealPassword(detail.value.id, historyId)
    ElMessageBox.alert(`历史密码（#${historyId}）：${res.password || '（空）'}`, '历史密码',
      { confirmButtonText: '关闭' }).catch(() => {})
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

// 表单
const formVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive<DeviceForm & { id?: number }>(blankForm())

function blankForm(): DeviceForm & { id?: number } {
  return {
    id: undefined, device_name: '', customer_id: null, device_type: '', brand: '', model: '',
    serial_number: '', network_type: '', ip_address: '', port: 22, username: '', password: '',
    login_method: 'SSH', location: '', interface: [], os_version: '', rule_version: '',
    is_maintenance: false, is_in_use: true, license_expiry: '', license_start: '',
    build_date: '', cert_expiry_date: '', remark: '',
  }
}

const formRules = {
  device_name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
}

function openCreate() {
  Object.assign(form, blankForm())
  formVisible.value = true
}

async function openEdit(d: Device) {
  Object.assign(form, blankForm(), {
    id: d.id, device_name: d.device_name, customer_id: d.customer_id, device_type: d.device_type,
    brand: d.brand, model: d.model, serial_number: d.serial_number, network_type: d.network_type,
    ip_address: d.ip_address, port: d.port, username: d.username, login_method: d.login_method,
    location: d.location, interface: [...d.interface], os_version: d.os_version,
    rule_version: d.rule_version, is_maintenance: d.is_maintenance, is_in_use: d.is_in_use,
    license_expiry: d.license_expiry, license_start: d.license_start, build_date: d.build_date,
    cert_expiry_date: d.cert_expiry_date, remark: d.remark,
  })
  detailVisible.value = false
  formVisible.value = true
}

async function save() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = { ...form }
    delete payload.id
    if (form.id) {
      await updateDevice(form.id, payload as DeviceForm)
      ui.toast('设备已更新', 'success')
    } else {
      await createDevice(payload as DeviceForm)
      ui.toast('设备已创建', 'success')
    }
    formVisible.value = false
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    saving.value = false
  }
}

async function onDelete(d: Device) {
  try {
    await ElMessageBox.confirm(`确定删除设备「${d.device_name}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDevice(d.id)
    ui.toast('已删除', 'success')
    reload()
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  }
}

function reload() {
  if (mode.value === 'table') {
    tableRef.value?.refresh()
  } else {
    loadTree()
  }
}

// 初始化字典
import { fetchDeviceDicts } from '@/api/dicts'
fetchDeviceDicts().then((d) => {
  brands.value = d.brands
  deviceTypes.value = d.device_types
  customers.value = d.customers
  // ?customer_id=X 直达表格模式（全局搜索/书签跳转）
  const cid = Number(route.query.customer_id)
  if (cid && !Number.isNaN(cid) && cid > 0) {
    const c = d.customers.find((x: { id: number; name: string }) => x.id === cid)
    tableCustomer.value = { id: cid, name: c?.name || `客户 #${cid}` }
    query.customer_id = cid
    mode.value = 'table'
    setTimeout(() => tableRef.value?.refresh(), 0)
  } else {
    loadTree()
  }
})
</script>

<style scoped>
.filter-card {
  margin-bottom: 12px;
}
.filter-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.filter-search {
  width: 220px;
  max-width: 100%;
}
.filter-item {
  width: 140px;
  max-width: 100%;
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.w-full {
  width: 100%;
}
.flex-gap {
  display: flex;
  gap: 6px;
  width: 100%;
}
.flex-gap .el-input {
  flex: 1;
}
.ml-1 {
  margin-left: 6px;
}
.mr-1 {
  margin-right: 4px;
}
.cell-muted {
  color: var(--itsm-text-muted);
}
.cust-leaf {
  display: flex; align-items: center; gap: 8px; padding: 9px 12px;
  font-size: 13px; cursor: pointer; border: 1px solid var(--itsm-border);
  border-radius: 8px; margin-bottom: 8px;
}
.cust-leaf:hover { background: var(--el-fill-color-light); }
.cust-leaf .tree-name { font-weight: 600; flex-shrink: 0; }
.scope-tag { font-weight: 500; }
.cell-danger {
  color: #f56c6c;
  font-weight: 600;
}
.cell-warn {
  color: #e6a23c;
}
.backup-list { margin-bottom: 8px; }
.backup-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.backup-compare-sel {
  flex: 1;
  min-width: 200px;
}
.diff-wrap {
  max-height: 70vh;
  overflow: auto;
}
.diff-row {
  display: flex;
  gap: 8px;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.5;
}
.diff-a,
.diff-b {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-all;
  padding: 1px 4px;
  min-width: 0;
}
.diff-equal { color: var(--itsm-text-muted); }
.diff-delete { background: #f56c6c22; color: #f56c6c; }
.diff-insert { background: #67c23a22; color: #67c23a; }
.diff-replace { background: #e6a23c22; color: #e6a23c; }
</style>
