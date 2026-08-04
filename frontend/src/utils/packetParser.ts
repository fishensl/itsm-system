/** 报文解析核心（移植自 static/js/tools.js 的 packet 管线，纯函数无 DOM） */

export interface RawFrame {
  ts: number
  bytes: Uint8Array
}

export interface PacketRecord {
  idx: number
  ts: number
  relTs: number
  src: { ip: string; mac: string; port: number | null }
  dst: { ip: string; mac: string; port: number | null }
  l3: string
  l4: string | null
  appProto: string | null
  tlsVersion: string | null
  domain: string | null
  length: number
  info: string
  flags: { syn: boolean; ack: boolean; fin: boolean; rst: boolean; psh: boolean } | null
  bytes: Uint8Array
}

export interface Session {
  l4: string
  ip1: string
  port1: number
  ip2: string
  port2: number
  appProto: string | null
  tsStart: number
  tsEnd: number
  frames: number
  bytes: number
  info: string
}

export function parseHexBytes(s: string): Uint8Array {
  const clean = s.replace(/[\s:.-]+/g, '').replace(/0x/gi, '')
  if (!/^[0-9a-fA-F]*$/.test(clean) || clean.length % 2) throw new Error('无效 HEX 字符串')
  const bytes = new Uint8Array(clean.length / 2)
  for (let i = 0; i < clean.length; i += 2) bytes[i / 2] = parseInt(clean.substr(i, 2), 16)
  return bytes
}

export function parseB64Bytes(s: string): Uint8Array {
  const bstr = atob(s.replace(/\s/g, ''))
  const bytes = new Uint8Array(bstr.length)
  for (let i = 0; i < bstr.length; i++) bytes[i] = bstr.charCodeAt(i)
  return bytes
}

function fmtMac(b: Uint8Array, off: number): string {
  const p: string[] = []
  for (let i = 0; i < 6; i++) p.push(b[off + i].toString(16).padStart(2, '0'))
  return p.join(':')
}

function fmtIp4(b: Uint8Array, off: number): string {
  return `${b[off]}.${b[off + 1]}.${b[off + 2]}.${b[off + 3]}`
}

function fmtIp6(b: Uint8Array, off: number): string {
  const parts: string[] = []
  for (let i = 0; i < 16; i += 2) parts.push(((b[off + i] << 8) | b[off + i + 1]).toString(16))
  return parts.join(':').replace(/(:0)+:/, '::').replace(/^0(::)/, '$1')
}

export function parsePcapAllFrames(bytes: Uint8Array): { frames: RawFrame[]; info: string } {
  if (bytes.length < 24 + 16) throw new Error('PCAP 文件长度不足')
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const magic = dv.getUint32(0, false)
  let littleEndian = false
  let nanoTs = false
  if (magic === 0xa1b2c3d4) { littleEndian = false; nanoTs = false }
  else if (magic === 0xa1b23c4d) { littleEndian = false; nanoTs = true }
  else if (magic === 0xd4c3b2a1) { littleEndian = true; nanoTs = false }
  else if (magic === 0x4d3cb2a1) { littleEndian = true; nanoTs = true }
  else throw new Error('非 PCAP 格式')
  const linktype = dv.getUint32(20, littleEndian)
  if (linktype !== 1) throw new Error(`暂只支持以太网 (LINKTYPE_ETHERNET=1)，当前 linktype=${linktype}`)
  const frames: RawFrame[] = []
  let off = 24
  while (off + 16 <= bytes.length && frames.length < 5000) {
    const tsSec = dv.getUint32(off, littleEndian)
    const tsFrac = dv.getUint32(off + 4, littleEndian)
    const inclLen = dv.getUint32(off + 8, littleEndian)
    if (inclLen <= 0 || inclLen > 65535) break
    if (off + 16 + inclLen > bytes.length) break
    const ts = tsSec + tsFrac / (nanoTs ? 1e9 : 1e6)
    frames.push({ ts, bytes: bytes.slice(off + 16, off + 16 + inclLen) })
    off += 16 + inclLen
  }
  return {
    frames,
    info: `PCAP (${littleEndian ? 'LE' : 'BE'}${nanoTs ? ', nano-ts' : ''}, linktype=Ethernet, ${frames.length} 帧)`,
  }
}

export function parsePcapngAllFrames(bytes: Uint8Array): { frames: RawFrame[]; info: string } {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  if (bytes.length < 12) throw new Error('PCAPNG 文件长度不足')
  if (dv.getUint32(0, false) !== 0x0a0d0d0a) throw new Error('非 PCAPNG 格式')
  const littleEndian = dv.getUint32(8, false) === 0x4d3c2b1a
  const frames: RawFrame[] = []
  let off = dv.getUint32(4, littleEndian)
  const tsResolution = 1e6
  while (off + 8 <= bytes.length && frames.length < 5000) {
    const blockType = dv.getUint32(off, littleEndian)
    const blockLen = dv.getUint32(off + 4, littleEndian)
    if (blockLen < 12 || off + blockLen > bytes.length) break
    if (blockType === 0x00000006) {
      const tsHigh = dv.getUint32(off + 12, littleEndian)
      const tsLow = dv.getUint32(off + 16, littleEndian)
      const capLen = dv.getUint32(off + 20, littleEndian)
      const dataStart = off + 28
      const ts64 = (tsHigh * 0x100000000 + tsLow) / tsResolution
      frames.push({ ts: ts64, bytes: bytes.slice(dataStart, dataStart + capLen) })
    } else if (blockType === 0x00000003) {
      const origLen = dv.getUint32(off + 8, littleEndian)
      const cap = Math.min(origLen, blockLen - 16)
      frames.push({ ts: 0, bytes: bytes.slice(off + 12, off + 12 + cap) })
    }
    off += blockLen
  }
  return { frames, info: `PCAPNG (${littleEndian ? 'LE' : 'BE'}, ${frames.length} 帧)` }
}

function extractAppLayer(rec: PacketRecord): void {
  const off = (rec as unknown as { _payloadOff?: number })._payloadOff
  if (off == null || off >= rec.bytes.length) return
  const b = rec.bytes
  if (rec.appProto === 'DNS') {
    const dnsStart = off
    if (b.length < dnsStart + 13) return
    const qdcount = (b[dnsStart + 4] << 8) | b[dnsStart + 5]
    if (qdcount < 1) return
    let p = dnsStart + 12
    const labels: string[] = []
    let safety = 0
    while (p < b.length && safety++ < 30) {
      const len = b[p]
      if (len === 0) break
      if ((len & 0xc0) === 0xc0) break
      if (len > 63 || p + 1 + len > b.length) return
      const lbl: string[] = []
      for (let i = 0; i < len; i++) lbl.push(String.fromCharCode(b[p + 1 + i]))
      labels.push(lbl.join(''))
      p += 1 + len
    }
    if (labels.length) {
      rec.domain = labels.join('.')
      rec.info = '查询 ' + rec.domain
    }
  } else if (rec.appProto === 'HTTP') {
    const end = Math.min(b.length, off + 1024)
    if (end - off < 8) return
    let s = ''
    for (let i = off; i < end; i++) {
      const c = b[i]
      s += (c >= 0x20 && c < 0x7f) || c === 0x0a || c === 0x0d ? String.fromCharCode(c) : ' '
    }
    const m = s.match(/^(GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH|CONNECT|TRACE)\s+(\S+)\s+HTTP\/[\d.]+/m)
    if (m) rec.info = `${m[1]} ${m[2]}`
    const h = s.match(/Host:\s*([^\r\n]+)/i)
    if (h) rec.domain = h[1].trim()
  } else if (rec.appProto === 'TLS') {
    if (b.length < off + 5 + 4) return
    if (b[off] !== 22) return
    if (b[off + 5] !== 1) return
    let p = off + 5 + 4 + 2 + 32
    if (p + 1 > b.length) return
    const sidLen = b[p]; p += 1 + sidLen
    if (p + 2 > b.length) return
    const csLen = (b[p] << 8) | b[p + 1]; p += 2 + csLen
    if (p + 1 > b.length) return
    const cmLen = b[p]; p += 1 + cmLen
    if (p + 2 > b.length) return
    const extLen = (b[p] << 8) | b[p + 1]; p += 2
    const extEnd = Math.min(b.length, p + extLen)
    let tlsVer: string | null = null
    while (p + 4 <= extEnd) {
      const t = (b[p] << 8) | b[p + 1]
      const l = (b[p + 2] << 8) | b[p + 3]
      const v = p + 4
      if (t === 0x0000 && v + 5 <= extEnd) {
        const snLen = (b[v + 3] << 8) | b[v + 4]
        if (v + 5 + snLen <= extEnd) {
          let name = ''
          for (let i = 0; i < snLen; i++) name += String.fromCharCode(b[v + 5 + i])
          rec.domain = name
        }
      } else if (t === 0x002b) {
        const sv = b[v]
        let q = v + 1
        while (q + 1 < v + 1 + sv) {
          const ver = (b[q] << 8) | b[q + 1]
          if (ver === 0x0304) tlsVer = 'TLSv1.3'
          else if (ver === 0x0303 && !tlsVer) tlsVer = 'TLSv1.2'
          q += 2
        }
      }
      p = v + l
    }
    if (!tlsVer) {
      const cv = (b[off + 5 + 4] << 8) | b[off + 5 + 4 + 1]
      if (cv === 0x0303) tlsVer = 'TLSv1.2'
      else if (cv === 0x0302) tlsVer = 'TLSv1.1'
    }
    rec.tlsVersion = tlsVer
    if (rec.domain) rec.info = 'ClientHello SNI=' + rec.domain
  } else if (rec.appProto === 'SSH') {
    const end = Math.min(b.length, off + 64)
    let s = ''
    for (let i = off; i < end; i++) {
      const c = b[i]
      if (c === 0x0d || c === 0x0a) break
      if (c >= 0x20 && c < 0x7f) s += String.fromCharCode(c)
    }
    if (s.startsWith('SSH-')) rec.info = s
  }
}

export function buildRecord(bytes: Uint8Array, idx: number, ts: number, tsBase: number): PacketRecord {
  const rec: PacketRecord = {
    idx,
    ts,
    relTs: ts > 0 ? ts - tsBase : 0,
    src: { ip: '', mac: '', port: null },
    dst: { ip: '', mac: '', port: null },
    l3: 'OTHER',
    l4: null,
    appProto: null,
    tlsVersion: null,
    domain: null,
    length: bytes.length,
    info: '',
    flags: null,
    bytes,
  }
  if (!bytes || bytes.length < 14) {
    rec.info = '长度不足'
    return rec
  }
  rec.src.mac = fmtMac(bytes, 6)
  rec.dst.mac = fmtMac(bytes, 0)
  const etherType = (bytes[12] << 8) | bytes[13]
  const off = 14
  const payload = rec as unknown as { _payloadOff?: number }
  if (etherType === 0x0806) {
    rec.l3 = 'ARP'
    if (bytes.length >= off + 28) {
      const op = (bytes[off + 6] << 8) | bytes[off + 7]
      rec.src.ip = fmtIp4(bytes, off + 14)
      rec.dst.ip = fmtIp4(bytes, off + 24)
      rec.info = op === 1 ? `谁是 ${rec.dst.ip}？告诉 ${rec.src.ip}`
        : op === 2 ? `${rec.src.ip} 在 ${fmtMac(bytes, off + 8)}` : `ARP op=${op}`
    }
  } else if (etherType === 0x0800 && bytes.length >= off + 20) {
    rec.l3 = 'IPv4'
    const ihl = (bytes[off] & 0x0f) * 4
    const proto = bytes[off + 9]
    rec.src.ip = fmtIp4(bytes, off + 12)
    rec.dst.ip = fmtIp4(bytes, off + 16)
    const l4 = off + ihl
    if (proto === 6 && bytes.length >= l4 + 20) {
      rec.l4 = 'TCP'
      rec.src.port = (bytes[l4] << 8) | bytes[l4 + 1]
      rec.dst.port = (bytes[l4 + 2] << 8) | bytes[l4 + 3]
      const flags = bytes[l4 + 13]
      rec.flags = {
        syn: !!(flags & 0x02), ack: !!(flags & 0x10), fin: !!(flags & 0x01),
        rst: !!(flags & 0x04), psh: !!(flags & 0x08),
      }
      const fn: string[] = []
      if (flags & 0x10) fn.push('ACK')
      if (flags & 0x08) fn.push('PSH')
      if (flags & 0x04) fn.push('RST')
      if (flags & 0x02) fn.push('SYN')
      if (flags & 0x01) fn.push('FIN')
      rec.info = `${rec.src.port} → ${rec.dst.port} [${fn.join(',') || '·'}]`
      payload._payloadOff = l4 + ((bytes[l4 + 12] >> 4) * 4)
    } else if (proto === 17 && bytes.length >= l4 + 8) {
      rec.l4 = 'UDP'
      rec.src.port = (bytes[l4] << 8) | bytes[l4 + 1]
      rec.dst.port = (bytes[l4 + 2] << 8) | bytes[l4 + 3]
      rec.info = `${rec.src.port} → ${rec.dst.port}`
      payload._payloadOff = l4 + 8
    } else if (proto === 1 && bytes.length >= l4 + 4) {
      rec.l4 = 'ICMP'
      const t = bytes[l4]
      const c = bytes[l4 + 1]
      const tn = ({ 0: '回显应答', 8: '回显请求', 3: '目的不可达', 11: '超时', 5: '重定向' } as Record<number, string>)[t] || `类型 ${t}`
      rec.info = `${tn} (code=${c})`
    } else {
      rec.info = `IP proto=${proto}`
    }
  } else if (etherType === 0x86dd) {
    rec.l3 = 'IPv6'
    if (bytes.length >= off + 40) {
      const nh = bytes[off + 6]
      rec.src.ip = fmtIp6(bytes, off + 8)
      rec.dst.ip = fmtIp6(bytes, off + 24)
      const l4 = off + 40
      if (nh === 6 && bytes.length >= l4 + 20) {
        rec.l4 = 'TCP'
        rec.src.port = (bytes[l4] << 8) | bytes[l4 + 1]
        rec.dst.port = (bytes[l4 + 2] << 8) | bytes[l4 + 3]
        payload._payloadOff = l4 + ((bytes[l4 + 12] >> 4) * 4)
        rec.info = `${rec.src.port} → ${rec.dst.port}`
      } else if (nh === 17 && bytes.length >= l4 + 8) {
        rec.l4 = 'UDP'
        rec.src.port = (bytes[l4] << 8) | bytes[l4 + 1]
        rec.dst.port = (bytes[l4 + 2] << 8) | bytes[l4 + 3]
        payload._payloadOff = l4 + 8
        rec.info = `${rec.src.port} → ${rec.dst.port}`
      } else if (nh === 58) {
        rec.l4 = 'ICMPv6'
        rec.info = 'ICMPv6'
      } else {
        rec.info = `IPv6 next=${nh}`
      }
    }
  } else {
    rec.info = '以太网 0x' + etherType.toString(16)
  }
  const sp = rec.src.port
  const dp = rec.dst.port
  if (rec.l4 === 'UDP' && (sp === 53 || dp === 53)) rec.appProto = 'DNS'
  else if (rec.l4 === 'TCP' && (sp === 443 || dp === 443)) rec.appProto = 'TLS'
  else if (rec.l4 === 'TCP' && [80, 8080, 8000].some((p) => p === sp || p === dp)) rec.appProto = 'HTTP'
  else if (rec.l4 === 'TCP' && (sp === 22 || dp === 22)) rec.appProto = 'SSH'
  extractAppLayer(rec)
  return rec
}

export function buildSessions(records: PacketRecord[]): Session[] {
  const map = new Map<string, Session>()
  for (const r of records) {
    if (!r.l4 || (r.l4 !== 'TCP' && r.l4 !== 'UDP')) continue
    if (r.src.port == null || r.dst.port == null) continue
    const a = `${r.src.ip}|${r.src.port}`
    const b = `${r.dst.ip}|${r.dst.port}`
    const swap = a > b
    const k1 = swap ? b : a
    const k2 = swap ? a : b
    const key = `${r.l4}|${k1}|${k2}`
    let s = map.get(key)
    if (!s) {
      const [ip1, p1] = k1.split('|')
      const [ip2, p2] = k2.split('|')
      s = {
        l4: r.l4, ip1, port1: +p1, ip2, port2: +p2,
        appProto: null, tsStart: r.ts, tsEnd: r.ts, frames: 0, bytes: 0, info: '',
      }
      map.set(key, s)
    }
    s.frames += 1
    s.bytes += r.length
    if (r.ts < s.tsStart) s.tsStart = r.ts
    if (r.ts > s.tsEnd) s.tsEnd = r.ts
    if (!s.appProto && r.appProto) s.appProto = r.appProto
    s.info = `${r.l4} ${s.ip1}:${s.port1} ↔ ${s.ip2}:${s.port2}`
  }
  return [...map.values()].sort((x, y) => y.bytes - x.bytes)
}

export function buildStats(records: PacketRecord[]) {
  const protoCount: Record<string, number> = {}
  const appCount: Record<string, number> = {}
  const ipCount: Record<string, number> = {}
  for (const r of records) {
    const p = r.l3 === 'IPv4' || r.l3 === 'IPv6' ? (r.l4 || 'IP') : r.l3
    protoCount[p] = (protoCount[p] || 0) + 1
    if (r.appProto) appCount[r.appProto] = (appCount[r.appProto] || 0) + 1
    if (r.src.ip) ipCount[r.src.ip] = (ipCount[r.src.ip] || 0) + 1
    if (r.dst.ip && r.dst.ip !== r.src.ip) ipCount[r.dst.ip] = (ipCount[r.dst.ip] || 0) + 1
  }
  return {
    total: records.length,
    protoCount: Object.entries(protoCount).sort((a, b) => b[1] - a[1]),
    appCount: Object.entries(appCount).sort((a, b) => b[1] - a[1]),
    topIps: Object.entries(ipCount).sort((a, b) => b[1] - a[1]).slice(0, 10),
  }
}
