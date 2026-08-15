<template>
  <el-card shadow="never" class="tool-card">
    <template #header>
      <div class="tool-header"><el-icon><Search /></el-icon> 报文分析（PCAP / HEX）</div>
    </template>

    <!-- 输入 -->
    <div class="pkt-input">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="file">文件</el-radio-button>
        <el-radio-button value="paste">粘贴</el-radio-button>
      </el-radio-group>

      <template v-if="mode === 'file'">
        <input ref="fileInput" type="file" class="file-input"
          accept=".pcap,.pcapng,.cap,.bin,.txt,.dump,.hex" />
      </template>
      <template v-else>
        <el-select v-model="fmt" size="small" style="width: 110px">
          <el-option label="HEX" value="hex" />
          <el-option label="Base64" value="base64" />
        </el-select>
        <el-input v-model="pasteData" size="small" placeholder="从以太网头开始的 HEX / Base64" clearable />
      </template>

      <div class="pkt-btns">
        <el-button type="primary" size="small" :loading="parsing" @click="doParse">解析</el-button>
        <el-button size="small" @click="doReset">重置</el-button>
      </div>
      <div class="pkt-hint">
        支持 .pcap/.pcapng/.cap（多帧）、.bin（原始字节）、.txt/.hex/.dump（HEX 文本）。
        <el-link type="primary" size="small" @click="loadSample">载入 TCP SYN 示例</el-link>
      </div>
    </div>

    <!-- 统计 -->
    <div v-if="records.length" class="pkt-stats">
      <el-tag size="small" type="info">{{ sourceInfo }}</el-tag>
      <el-tag v-for="[p, n] in stats.protoCount.slice(0, 6)" :key="p" size="small">{{ p }}: {{ n }}</el-tag>
      <el-tag v-for="[a, n] in stats.appCount.slice(0, 4)" :key="a" size="small" type="warning">{{ a }}: {{ n }}</el-tag>
    </div>

    <!-- 视图切换 + 列表 -->
    <div v-if="records.length" class="pkt-main">
      <div class="pkt-navs">
        <div class="nav-title">数据包</div>
        <div v-for="v in VIEWS" :key="v.key" class="pkt-nav" :class="{ active: view === v.key }"
          @click="view = v.key">{{ v.label }}</div>
      </div>
      <div class="pkt-list">
        <div class="pkt-filter">
          <el-input v-model="filter.ip" size="small" placeholder="IP" style="width: 150px" clearable />
          <el-input v-model="filter.port" size="small" placeholder="端口" style="width: 90px" clearable />
          <el-input v-model="filter.app" size="small" placeholder="协议 HTTP/DNS/TLS" style="width: 150px" clearable />
          <el-button size="small" type="primary" plain @click="applyFilter">查找</el-button>
          <span class="count">{{ filtered.length }} / {{ records.length }}</span>
        </div>
        <div v-if="isMobile" class="packet-cards">
          <button v-for="row in filtered" :key="row.idx" type="button" class="packet-card"
            @click="onSelect(row)">
            <span class="packet-card-head">
              <b>#{{ row.idx + 1 }}</b>
              <span>{{ row.relTs.toFixed(3) }}s</span>
              <el-tag size="small" :type="protoType(row.l4 || row.l3)">{{ row.l4 || row.l3 }}</el-tag>
              <span>{{ row.length }}B</span>
            </span>
            <span class="packet-endpoints mono">
              {{ row.src.ip || row.src.mac || '-' }}<template v-if="row.src.port">:{{ row.src.port }}</template>
              →
              {{ row.dst.ip || row.dst.mac || '-' }}<template v-if="row.dst.port">:{{ row.dst.port }}</template>
            </span>
            <span class="packet-info">{{ row.info || '-' }}</span>
          </button>
        </div>
        <el-table v-else :data="filtered" size="small" border max-height="360" highlight-current-row
          @current-change="onSelect">
          <el-table-column label="#" width="56">
            <template #default="{ row }">{{ row.idx + 1 }}</template>
          </el-table-column>
          <el-table-column label="时间" width="90">
            <template #default="{ row }">{{ row.relTs.toFixed(3) }}</template>
          </el-table-column>
          <el-table-column label="源" min-width="150">
            <template #default="{ row }">
              <span class="mono">{{ row.src.ip || row.src.mac || '-' }}</span>
              <span v-if="row.src.port" class="mono muted">:{{ row.src.port }}</span>
            </template>
          </el-table-column>
          <el-table-column label="目的" min-width="150">
            <template #default="{ row }">
              <span class="mono">{{ row.dst.ip || row.dst.mac || '-' }}</span>
              <span v-if="row.dst.port" class="mono muted">:{{ row.dst.port }}</span>
            </template>
          </el-table-column>
          <el-table-column label="协议" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="protoType(row.l4 || row.l3)">{{ row.l4 || row.l3 }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="长度" width="70">
            <template #default="{ row }">{{ row.length }}</template>
          </el-table-column>
          <el-table-column label="信息" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.info }}
              <el-tag v-if="row.tlsVersion" size="small" type="info">{{ row.tlsVersion }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!filtered.length" description="无匹配数据包" :image-size="40" />
      </div>
    </div>

    <!-- 会话 -->
    <div v-if="view === 'sessions' && records.length" class="pkt-sessions">
      <div v-if="isMobile" class="packet-cards">
        <div v-for="row in sessions" :key="`${row.l4}-${row.ip1}-${row.port1}-${row.ip2}-${row.port2}`"
          class="packet-card">
          <span class="packet-card-head">
            <el-tag size="small">{{ row.l4 }}</el-tag>
            <span>{{ row.frames }} 包</span>
            <span>{{ row.bytes }} 字节</span>
          </span>
          <span class="packet-endpoints mono">{{ row.ip1 }}:{{ row.port1 }} → {{ row.ip2 }}:{{ row.port2 }}</span>
          <el-tag v-if="row.appProto" size="small" type="warning">{{ row.appProto }}</el-tag>
        </div>
      </div>
      <el-table v-else :data="sessions" size="small" border max-height="360">
        <el-table-column prop="l4" label="协议" width="70" />
        <el-table-column label="会话" min-width="280">
          <template #default="{ row }">
            <span class="mono">{{ row.ip1 }}:{{ row.port1 }}</span>
            <el-icon class="muted"><Right /></el-icon>
            <span class="mono">{{ row.ip2 }}:{{ row.port2 }}</span>
            <el-tag v-if="row.appProto" size="small" type="warning" class="ml-1">{{ row.appProto }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="包数" width="70" prop="frames" />
        <el-table-column label="字节" width="90" prop="bytes" />
      </el-table>
    </div>

    <!-- 详情 -->
    <el-drawer v-model="detailVisible" title="数据包详情" :size="isMobile ? '100%' : '560px'">
      <template v-if="selected">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="编号">#{{ selected.idx + 1 }}</el-descriptions-item>
          <el-descriptions-item label="长度">{{ selected.length }} 字节</el-descriptions-item>
          <el-descriptions-item label="源">{{ selected.src.ip || '-' }}<span v-if="selected.src.port">:{{ selected.src.port }}</span></el-descriptions-item>
          <el-descriptions-item label="目的">{{ selected.dst.ip || '-' }}<span v-if="selected.dst.port">:{{ selected.dst.port }}</span></el-descriptions-item>
          <el-descriptions-item label="MAC">{{ selected.src.mac }} → {{ selected.dst.mac }}</el-descriptions-item>
          <el-descriptions-item label="协议">{{ selected.l4 || selected.l3 }}</el-descriptions-item>
          <el-descriptions-item v-if="selected.domain" label="域名" :span="2">{{ selected.domain }}</el-descriptions-item>
          <el-descriptions-item v-if="selected.tlsVersion" label="TLS" :span="2">{{ selected.tlsVersion }}</el-descriptions-item>
          <el-descriptions-item label="信息" :span="2">{{ selected.info || '-' }}</el-descriptions-item>
        </el-descriptions>
        <el-divider content-position="left">十六进制</el-divider>
        <pre class="hex-dump">{{ hexDump }}</pre>
      </template>
    </el-drawer>
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Search, Right } from '@element-plus/icons-vue'
import { useUiStore } from '@/stores/ui'
import { useMobile } from '@/utils/useMobile'
import {
  parseHexBytes, parseB64Bytes, parsePcapAllFrames, parsePcapngAllFrames,
  buildRecord, buildSessions, buildStats,
  type PacketRecord, type Session,
} from '@/utils/packetParser'

const ui = useUiStore()
const { isMobile } = useMobile()
const mode = ref<'file' | 'paste'>('paste')
const fmt = ref('hex')
const pasteData = ref('')
const fileInput = ref<HTMLInputElement>()
const parsing = ref(false)
const sourceInfo = ref('')
const records = ref<PacketRecord[]>([])
const sessions = ref<Session[]>([])
const view = ref<string>('frames')
const filter = ref({ ip: '', port: '', app: '' })
const detailVisible = ref(false)
const selected = ref<PacketRecord | null>(null)

const VIEWS = [
  { key: 'frames', label: '数据包' },
  { key: 'sessions', label: '通信会话' },
]

const stats = computed(() => buildStats(records.value))

const filtered = computed(() => {
  const { ip, port, app } = filter.value
  if (!ip && !port && !app) return records.value
  return records.value.filter((r) => {
    if (ip && !(r.src.ip.includes(ip) || r.dst.ip.includes(ip))) return false
    if (port && !(String(r.src.port ?? '') === port || String(r.dst.port ?? '') === port)) return false
    if (app && !(r.appProto || '').toLowerCase().includes(app.toLowerCase())) return false
    return true
  })
})

const hexDump = computed(() => {
  const b = selected.value?.bytes
  if (!b) return ''
  const lines: string[] = []
  for (let off = 0; off < b.length; off += 16) {
    const hex: string[] = []
    const asc: string[] = []
    for (let i = 0; i < 16 && off + i < b.length; i++) {
      const c = b[off + i]
      hex.push(c.toString(16).padStart(2, '0'))
      asc.push(c >= 0x20 && c < 0x7f ? String.fromCharCode(c) : '.')
    }
    lines.push(`${off.toString(16).padStart(4, '0')}  ${hex.join(' ').padEnd(47)}  ${asc.join('')}`)
  }
  return lines.join('\n')
})

function protoType(p: string) {
  if (p === 'TCP') return 'primary'
  if (p === 'UDP') return 'success'
  if (p === 'ARP') return 'warning'
  if (p === 'ICMP' || p === 'ICMPv6') return 'danger'
  return 'info'
}

function loadFrames(raw: Array<{ ts: number; bytes: Uint8Array }>, info: string) {
  if (!raw.length) {
    ui.toast('未识别到任何数据包', 'error')
    return
  }
  const tsBase = raw[0].ts || 0
  records.value = raw.map((f, i) => buildRecord(f.bytes, i, f.ts || 0, tsBase))
  sessions.value = buildSessions(records.value)
  sourceInfo.value = info
  view.value = 'frames'
  detailVisible.value = false
  selected.value = null
}

async function doParse() {
  parsing.value = true
  try {
    if (mode.value === 'paste') {
      const data = pasteData.value.trim()
      if (!data) {
        ui.toast('请输入报文数据', 'info')
        return
      }
      const bytes = fmt.value === 'hex' ? parseHexBytes(data) : parseB64Bytes(data)
      loadFrames([{ ts: 0, bytes }], `粘贴 (${bytes.length} 字节)`)
    } else {
      const file = fileInput.value?.files?.[0]
      if (!file) {
        ui.toast('请选择文件', 'info')
        return
      }
      const ext = (file.name.split('.').pop() || '').toLowerCase()
      const ab = await file.arrayBuffer()
      const u8 = new Uint8Array(ab)
      if (ext === 'pcap' || ext === 'cap') {
        const r = parsePcapAllFrames(u8)
        loadFrames(r.frames, `${file.name} → ${r.info}`)
      } else if (ext === 'pcapng') {
        const r = parsePcapngAllFrames(u8)
        loadFrames(r.frames, `${file.name} → ${r.info}`)
      } else if (ext === 'txt' || ext === 'hex' || ext === 'dump') {
        const text = await file.text()
        const bytes = parseHexBytes(text)
        loadFrames([{ ts: 0, bytes }], `${file.name} (HEX 文本, ${bytes.length} 字节)`)
      } else if (ext === 'bin') {
        loadFrames([{ ts: 0, bytes: u8 }], `${file.name} (原始字节, ${u8.length} 字节)`)
      } else {
        if (u8.length >= 4) {
          const m = (u8[0] << 24 | u8[1] << 16 | u8[2] << 8 | u8[3]) >>> 0
          if (m === 0xa1b2c3d4 || m === 0xd4c3b2a1 || m === 0xa1b23c4d || m === 0x4d3cb2a1) {
            const r = parsePcapAllFrames(u8)
            loadFrames(r.frames, `${file.name} → ${r.info}`)
          } else if (m === 0x0a0d0d0a) {
            const r = parsePcapngAllFrames(u8)
            loadFrames(r.frames, `${file.name} → ${r.info}`)
          } else {
            loadFrames([{ ts: 0, bytes: u8 }], `${file.name} (自动识别为原始字节)`)
          }
        } else {
          throw new Error('文件过小')
        }
      }
    }
  } catch (e) {
    ui.toast(`解析失败: ${(e as Error).message}`, 'error')
  } finally {
    parsing.value = false
  }
}

function doReset() {
  records.value = []
  sessions.value = []
  sourceInfo.value = ''
  pasteData.value = ''
  filter.value = { ip: '', port: '', app: '' }
  detailVisible.value = false
  selected.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function applyFilter() {
  /* computed 已联动 */
}

function onSelect(row: PacketRecord | null) {
  if (row) {
    selected.value = row
    detailVisible.value = true
  }
}

function loadSample() {
  mode.value = 'paste'
  fmt.value = 'hex'
  pasteData.value = '001122334455aabbccddeeff080045000028000040004006abcd0a0a0a01c0a801010050d4310000000100000000500240007f000000'
  doParse()
}
</script>

<style scoped>
.tool-header { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.pkt-input { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.file-input { max-width: 320px; }
.pkt-btns { display: flex; gap: 8px; }
.pkt-hint { width: 100%; font-size: 12px; color: var(--itsm-text-muted); }
.pkt-stats { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; }
.pkt-main { display: flex; gap: 12px; margin-top: 12px; }
.pkt-navs { flex: 0 0 110px; }
.nav-title { font-size: 12px; font-weight: 600; color: var(--itsm-text-muted); margin: 4px 0; }
.pkt-nav {
  padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 13px;
  color: var(--itsm-text);
}
.pkt-nav:hover { background: var(--el-fill-color-light); }
.pkt-nav.active { background: var(--itsm-primary); color: var(--itsm-text-inverse); }
.pkt-list { flex: 1; min-width: 0; }
.pkt-filter { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.count { font-size: 12px; color: var(--itsm-text-muted); margin-left: auto; }
.mono { font-family: var(--font-mono, monospace); font-size: 12px; }
.muted { color: var(--itsm-text-muted); }
.ml-1 { margin-left: 4px; }
.hex-dump {
  font-family: var(--font-mono, monospace); font-size: 12px; line-height: 1.6;
  background: var(--el-fill-color-light); padding: 10px; border-radius: 6px;
  overflow-x: auto; margin: 0;
}
.packet-cards { display: grid; gap: 8px; }
.packet-card {
  display: grid; gap: 6px; width: 100%; padding: 10px; text-align: left;
  color: var(--itsm-text); background: var(--itsm-card-bg);
  border: 1px solid var(--itsm-border); border-radius: var(--itsm-radius-md);
}
button.packet-card { cursor: pointer; }
button.packet-card:active { border-color: var(--el-color-primary); }
.packet-card-head { display: flex; align-items: center; gap: 8px; color: var(--itsm-text-muted); }
.packet-endpoints { overflow-wrap: anywhere; }
.packet-info { color: var(--itsm-text-muted); font-size: var(--itsm-font-xs); }
@media (max-width: 767px) {
  .pkt-main { display: block; }
  .pkt-navs { display: flex; gap: 6px; margin-bottom: 8px; overflow-x: auto; }
  .nav-title { display: none; }
  .pkt-nav { white-space: nowrap; }
  .pkt-filter :deep(.el-input) { width: calc(50% - 3px) !important; }
  .count { width: 100%; margin-left: 0; }
}
</style>
