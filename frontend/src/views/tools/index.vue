<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">网络工具</h2>
    </div>

    <el-row :gutter="12">
      <!-- IP 计算 -->
      <el-col :xs="24" :sm="12">
        <el-card shadow="never" class="tool-card" :class="{ 'tool-active': highlightTool === 'network' }">
          <template #header>
            <div class="tool-header"><el-icon><Monitor /></el-icon> IP 地址计算</div>
          </template>
          <el-radio-group v-model="ipMode" class="ip-mode">
            <el-radio-button value="ipmask">IP + 掩码</el-radio-button>
            <el-radio-button value="cidr">CIDR</el-radio-button>
          </el-radio-group>
          <template v-if="ipMode === 'ipmask'">
            <div class="tool-field">
              <el-input v-model="ipForm.ip" placeholder="IP 地址，如 192.168.1.10" clearable
                @keyup.enter="runIpCalc" />
            </div>
            <div class="tool-field">
              <el-input v-model="ipForm.mask" placeholder="子网掩码，如 255.255.255.0 或 24" clearable
                @keyup.enter="runIpCalc" />
            </div>
          </template>
          <div v-else class="tool-field">
            <el-input v-model="ipForm.cidr" placeholder="CIDR，如 10.0.0.0/8" clearable
              @keyup.enter="runIpCalc" />
          </div>
          <el-button type="primary" :loading="ipLoading" @click="runIpCalc">计算</el-button>

          <el-descriptions v-if="ipResult" :column="2" border size="small" class="tool-result">
            <el-descriptions-item label="网络地址">{{ ipResult.network }}</el-descriptions-item>
            <el-descriptions-item label="广播地址">{{ ipResult.broadcast }}</el-descriptions-item>
            <el-descriptions-item label="可用起始">{{ ipResult.first }}</el-descriptions-item>
            <el-descriptions-item label="可用结束">{{ ipResult.last }}</el-descriptions-item>
            <el-descriptions-item label="可用主机数">{{ ipResult.hosts }}</el-descriptions-item>
            <el-descriptions-item label="子网掩码">{{ ipResult.mask }}（/{{ ipResult.mask_bits }}）</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <!-- 进制转换 -->
      <el-col :xs="24" :sm="12">
        <el-card shadow="never" class="tool-card" :class="{ 'tool-active': highlightTool === 'convert' }">
          <template #header>
            <div class="tool-header"><el-icon><DataAnalysis /></el-icon> 进制转换</div>
          </template>
          <div class="tool-field">
            <el-input v-model="convertForm.value" placeholder="输入数值，如 FF / 255 / 1010" clearable
              @keyup.enter="runConvert" />
          </div>
          <div class="tool-field convert-row">
            <el-select v-model="convertForm.from_base" class="convert-base">
              <el-option v-for="b in BASES" :key="b" :label="`${b} 进制`" :value="b" />
            </el-select>
            <el-icon class="convert-arrow"><Right /></el-icon>
            <el-select v-model="convertForm.to_base" class="convert-base">
              <el-option v-for="b in BASES" :key="b" :label="`${b} 进制`" :value="b" />
            </el-select>
          </div>
          <el-button type="primary" :loading="convertLoading" @click="runConvert">转换</el-button>

          <div v-if="convertResult" class="tool-result">
            <div class="convert-result-line">
              <span class="convert-label">结果（{{ convertResult.to_base }} 进制）</span>
              <code class="convert-value">{{ convertResult.result }}</code>
            </div>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="二进制">{{ convertResult.binary }}</el-descriptions-item>
              <el-descriptions-item label="八进制">{{ convertResult.octal }}</el-descriptions-item>
              <el-descriptions-item label="十进制">{{ convertResult.decimal }}</el-descriptions-item>
              <el-descriptions-item label="十六进制">{{ convertResult.hex }}</el-descriptions-item>
            </el-descriptions>
          </div>
        </el-card>
      </el-col>

      <!-- MAC 格式化 -->
      <el-col :xs="24" :sm="12">
        <el-card shadow="never" class="tool-card">
          <template #header>
            <div class="tool-header"><el-icon><Link /></el-icon> MAC 地址格式化</div>
          </template>
          <div class="tool-field">
            <el-input v-model="macForm.mac" placeholder="如 AA-BB-CC-DD-EE-FF 或 aabb.ccdd.eeff" clearable
              @keyup.enter="runMac" />
          </div>
          <el-button type="primary" :loading="macLoading" @click="runMac">格式化</el-button>

          <el-descriptions v-if="macResult" :column="2" border size="small" class="tool-result">
            <el-descriptions-item label="标准格式（推荐）">{{ macResult.result }}</el-descriptions-item>
            <el-descriptions-item label="连字符">{{ macResult.dash }}</el-descriptions-item>
            <el-descriptions-item label="点分格式">{{ macResult.dot }}</el-descriptions-item>
            <el-descriptions-item label="无分隔符">{{ macResult.plain }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <!-- 报文分析 -->
      <el-col :span="24" :class="{ 'tool-active': highlightTool === 'packet' }">
        <PacketAnalyzer />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Monitor, DataAnalysis, Link, Right } from '@element-plus/icons-vue'
import { useUiStore } from '@/stores/ui'
import { ipCalc, convertBase, formatMac, type IpCalcResult, type ConvertResult, type MacFormatResult } from '@/api/tools'
import PacketAnalyzer from './PacketAnalyzer.vue'

const ui = useUiStore()
const BASES = [2, 8, 10, 16]

// 侧栏入口（/app/tools?tool=network 等）高亮对应工具卡片
const route = useRoute()
const highlightTool = ref<'network' | 'convert' | 'packet' | ''>('')
watch(
  () => route.query.tool,
  (tool) => {
    highlightTool.value = (['network', 'convert', 'packet'].includes(String(tool))
      ? String(tool)
      : '') as typeof highlightTool.value
  },
  { immediate: true },
)

// IP 计算
const ipMode = ref<'ipmask' | 'cidr'>('ipmask')
const ipForm = reactive<{ ip: string; mask: string; cidr: string }>({ ip: '', mask: '', cidr: '' })
const ipResult = ref<IpCalcResult | null>(null)
const ipLoading = ref(false)

async function runIpCalc() {
  ipLoading.value = true
  try {
    ipResult.value = await ipCalc(
      ipMode.value === 'cidr'
        ? { cidr: ipForm.cidr }
        : { ip: ipForm.ip, mask: ipForm.mask },
    )
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    ipLoading.value = false
  }
}

// 进制转换
const convertForm = reactive<{ value: string; from_base: number; to_base: number }>({
  value: '', from_base: 10, to_base: 16,
})
const convertResult = ref<ConvertResult | null>(null)
const convertLoading = ref(false)

async function runConvert() {
  convertLoading.value = true
  try {
    convertResult.value = await convertBase({ ...convertForm })
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    convertLoading.value = false
  }
}

// MAC 格式化
const macForm = reactive<{ mac: string }>({ mac: '' })
const macResult = ref<MacFormatResult | null>(null)
const macLoading = ref(false)

async function runMac() {
  macLoading.value = true
  try {
    macResult.value = await formatMac({ mac: macForm.mac })
  } catch (e) {
    ui.toast((e as Error).message, 'error')
  } finally {
    macLoading.value = false
  }
}
</script>

<style scoped>
.tool-card { margin-bottom: 12px; }
.tool-card.tool-active,
.tool-active :deep(.tool-card) {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary);
}
.tool-header { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.ip-mode { margin-bottom: 10px; }
.tool-field { margin-bottom: 10px; }
.tool-result { margin-top: 14px; }
.convert-row { display: flex; align-items: center; gap: 8px; }
.convert-base { width: 140px; }
.convert-arrow { color: var(--itsm-text-muted); }
.convert-result-line { display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 10px; }
.convert-label { color: var(--itsm-text-muted); font-size: 13px; }
.convert-value { font-size: 18px; font-weight: 700; color: var(--el-color-primary);
  font-family: var(--font-mono, monospace); word-break: break-all; }
</style>
