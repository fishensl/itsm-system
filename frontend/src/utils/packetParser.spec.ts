import { describe, it, expect } from 'vitest'
import { parseHexBytes, buildRecord, buildSessions, buildStats, parsePcapAllFrames } from '@/utils/packetParser'

// TCP SYN: 以太网(14) + IPv4(20) + TCP(20)
const SYN_HEX =
  '001122334455aabbccddeeff0800' + // Ethernet
  '45000028000040004006abcd' + '0a0a0a01' + 'c0a80101' + // IPv4
  '0050d4310000000100000000' + '5002' + '4000' + '7f000000' // TCP SYN

describe('packetParser', () => {
  it('parseHexBytes 解析并校验', () => {
    const b = parseHexBytes('aa bb-cc:dd.ee ff')
    expect(b.length).toBe(6)
    expect(Array.from(b)).toEqual([0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff])
    expect(() => parseHexBytes('xyz')).toThrow()
  })

  it('buildRecord 解析 TCP SYN 帧', () => {
    const rec = buildRecord(parseHexBytes(SYN_HEX), 0, 0, 0)
    expect(rec.l3).toBe('IPv4')
    expect(rec.l4).toBe('TCP')
    expect(rec.src.ip).toBe('10.10.10.1')
    expect(rec.dst.ip).toBe('192.168.1.1')
    expect(rec.src.port).toBe(80)
    expect(rec.dst.port).toBe(54321)
    expect(rec.flags?.syn).toBe(true)
    expect(rec.info).toContain('SYN')
  })

  it('buildSessions 聚合会话', () => {
    const bytes = parseHexBytes(SYN_HEX)
    const recs = [buildRecord(bytes, 0, 0, 0), buildRecord(bytes, 1, 1, 0)]
    const sessions = buildSessions(recs)
    expect(sessions.length).toBe(1)
    expect(sessions[0].frames).toBe(2)
  })

  it('buildStats 统计协议', () => {
    const recs = [buildRecord(parseHexBytes(SYN_HEX), 0, 0, 0)]
    const s = buildStats(recs)
    expect(s.total).toBe(1)
    expect(s.protoCount[0]).toEqual(['TCP', 1])
  })

  it('parsePcapAllFrames 解析 pcap 头', () => {
    // 构造最小 pcap：24 字节头 + 1 帧（16 头 + 帧数据）
    const bytes = new Uint8Array(24 + 16 + 54)
    const dv = new DataView(bytes.buffer)
    dv.setUint32(0, 0xa1b2c3d4, false) // magic BE
    dv.setUint16(4, 2, false)
    dv.setUint16(6, 4, false)
    dv.setUint32(20, 1, false) // linktype ethernet
    dv.setUint32(24 + 8, 54, false) // incl_len
    bytes.set(parseHexBytes(SYN_HEX), 24 + 16)
    const r = parsePcapAllFrames(bytes)
    expect(r.frames.length).toBe(1)
    expect(r.frames[0].bytes.length).toBe(54)
  })
})
