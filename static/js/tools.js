// ============================ 工具函数 ============================
function copyText(t) {
    if (!t) return;
    navigator.clipboard.writeText(t).then(() => { showToast('已复制', 'success'); });
}

// ============================ IP 计算器 ============================
function ip2int(ip) {
    const p = ip.split('.').map(Number);
    if (p.length !== 4 || p.some(n => isNaN(n) || n < 0 || n > 255)) throw new Error('无效 IP');
    return ((p[0]<<24) | (p[1]<<16) | (p[2]<<8) | p[3]) >>> 0;
}
function int2ip(n) {
    return [(n>>>24)&0xff, (n>>>16)&0xff, (n>>>8)&0xff, n&0xff].join('.');
}
function maskFromCidr(cidr) {
    if (cidr === 0) return 0;
    return (0xffffffff << (32 - cidr)) >>> 0;
}

function updateIPCalcMask() {
    const v = document.getElementById('ipCalcVersion').value;
    const sel = document.getElementById('ipCalcMask');
    sel.innerHTML = '';
    if (v === 'ipv6') {
        for (let i = 48; i <= 128; i += 8) {
            sel.innerHTML += `<option value="${i}" ${i===64?'selected':''}>/${i}</option>`;
        }
    } else {
        const masks = [
            [8, '255.0.0.0 (A类)'], [16, '255.255.0.0 (B类)'], [24, '255.255.255.0 (C类)'],
            [25, '255.255.255.128'], [26, '255.255.255.192'], [27, '255.255.255.224'],
            [28, '255.255.255.240'], [29, '255.255.255.248'], [30, '255.255.255.252'],
            [31, '255.255.255.254'], [32, '255.255.255.255']
        ];
        masks.forEach(m => {
            const sel2 = m[0] === 24 ? 'selected' : '';
            sel.innerHTML += `<option value="${m[0]}" ${sel2}>/${m[0]} - ${m[1]}</option>`;
        });
    }
}

function calcIP() {
    const v = document.getElementById('ipCalcVersion').value;
    const input = document.getElementById('ipCalcInput').value.trim();
    if (!input) { showToast('请输入 IP', 'info'); return; }
    if (v === 'ipv6') {
        document.getElementById('ipCalcResult').style.display = 'block';
        document.getElementById('ipCalcResult').innerHTML = '<div class="alert alert-warning">IPv6 计算暂未实现，请用浏览器原生 URL.parse 或专业工具。</div>';
        return;
    }
    try {
        let ip = input, cidr = parseInt(document.getElementById('ipCalcMask').value);
        if (input.includes('/')) {
            ip = input.split('/')[0];
            cidr = parseInt(input.split('/')[1]);
        }
        const ipInt = ip2int(ip);
        const mask = maskFromCidr(cidr);
        const network = ipInt & mask;
        const broadcast = (network | (~mask >>> 0)) >>> 0;
        const total = cidr === 32 ? 1 : (cidr === 31 ? 2 : (Math.pow(2, 32-cidr)));
        const usable = cidr >= 31 ? total : (total - 2);
        const first = cidr >= 31 ? network : (network + 1);
        const last = cidr >= 31 ? broadcast : (broadcast - 1);
        const wildcard = (~mask) >>> 0;
        const cls = ipInt < 0x80000000 ? 'A' : ipInt < 0xc0000000 ? 'B' : ipInt < 0xe0000000 ? 'C' : ipInt < 0xf0000000 ? 'D(组播)' : 'E(保留)';
        const isPrivate = (ipInt >= 0x0a000000 && ipInt <= 0x0affffff) || (ipInt >= 0xac100000 && ipInt <= 0xac1fffff) || (ipInt >= 0xc0a80000 && ipInt <= 0xc0a8ffff);
        document.getElementById('ipCalcResult').style.display = 'block';
        document.getElementById('ipCalcResult').innerHTML = `
        <div class="info-grid">
            <div class="ig"><span class="k">网络地址</span><code>${int2ip(network)}/${cidr}</code></div>
            <div class="ig"><span class="k">广播地址</span><code>${int2ip(broadcast)}</code></div>
            <div class="ig"><span class="k">子网掩码</span><code>${int2ip(mask)}</code></div>
            <div class="ig"><span class="k">反掩码</span><code>${int2ip(wildcard)}</code></div>
            <div class="ig"><span class="k">总地址数</span><code>${total.toLocaleString()}</code></div>
            <div class="ig"><span class="k">可用主机</span><code>${usable.toLocaleString()}</code></div>
            <div class="ig" style="grid-column:1/-1"><span class="k">可用范围</span><code>${int2ip(first)} - ${int2ip(last)}</code></div>
            <div class="ig" style="grid-column:1/-1"><span class="k">地址类别</span><span>${cls} 类 ${isPrivate ? '<span class="badge bg-info ms-1">私有</span>' : '<span class="badge bg-success ms-1">公网</span>'}</span></div>
        </div>`;
    } catch(e) { showToast('计算失败: ' + e.message, 'danger'); }
}

// ============================ 子网划分 ============================
function calcSubnet() {
    const input = document.getElementById('subnetInput').value.trim();
    const count = parseInt(document.getElementById('subnetCount').value);
    if (!input || !input.includes('/')) { showToast('请输入网络/CIDR', 'info'); return; }
    if (count < 2 || count > 256) { showToast('数量需 2-256', 'warning'); return; }
    try {
        const [ip, cidrStr] = input.split('/');
        const baseCidr = parseInt(cidrStr);
        const bits = Math.ceil(Math.log2(count));
        const newCidr = baseCidr + bits;
        if (newCidr > 30) { showToast('子网过多，前缀超过 /30', 'warning'); return; }
        const baseInt = ip2int(ip) & maskFromCidr(baseCidr);
        const subSize = Math.pow(2, 32 - newCidr);
        const rows = [];
        for (let i = 0; i < count; i++) {
            const net = baseInt + i * subSize;
            const bc = net + subSize - 1;
            const fh = newCidr >= 31 ? net : net + 1;
            const lh = newCidr >= 31 ? bc : bc - 1;
            rows.push(`<tr><td>${i+1}</td><td><code>${int2ip(net)}/${newCidr}</code></td><td><code>${int2ip(fh)} - ${int2ip(lh)}</code></td><td><code>${int2ip(bc)}</code></td></tr>`);
        }
        document.getElementById('subnetResult').style.display = 'block';
        document.getElementById('subnetResult').innerHTML = `<table class="table table-sm table-bordered mb-0"><thead><tr><th>#</th><th>子网</th><th>可用范围</th><th>广播</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
    } catch(e) { showToast('划分失败: ' + e.message, 'danger'); }
}

// 合并入口：IP 计算 + 子网划分共用同一输入。
// 输入未带 /CIDR 时用掩码下拉补全；归一化后的 CIDR 同步到隐藏 subnetInput 供 calcSubnet 使用。
function calcIpAndSubnet() {
    const raw = document.getElementById('ipCalcInput').value.trim();
    if (!raw) { showToast('请输入 IP', 'info'); return; }
    // 归一化为 ip/cidr（calcIP 自身已能处理带/不带 CIDR，这里只为 calcSubnet 准备）
    let cidr = parseInt(document.getElementById('ipCalcMask').value);
    let ipPart = raw;
    if (raw.includes('/')) {
        ipPart = raw.split('/')[0];
        cidr = parseInt(raw.split('/')[1]);
    }
    document.getElementById('subnetInput').value = ipPart + '/' + cidr;
    // IP 详情
    calcIP();
    // 子网划分（数量<2 时不划分，隐藏结果）
    const count = parseInt(document.getElementById('subnetCount').value) || 1;
    const subRes = document.getElementById('subnetResult');
    if (count >= 2) {
        calcSubnet();
    } else {
        subRes.style.display = 'none';
        subRes.innerHTML = '';
    }
}

// ============================ MAC 工具 ============================
// 常见网络/IT 厂商 OUI（前 6 位 hex）→ 厂商名
const OUI_DB = {
    // 华为
    '001882':'Huawei','002568':'Huawei','00259E':'Huawei','002756':'Huawei','002A6A':'Huawei',
    '002B7E':'Huawei','004088':'Huawei','005A13':'Huawei','00664B':'Huawei','009ACD':'Huawei',
    '00E0FC':'Huawei','087A4C':'Huawei','0C37DC':'Huawei','0C45BA':'Huawei','107BEF':'Huawei',
    '141A51':'Huawei','144E2B':'Huawei','181D36':'Huawei','1C1D67':'Huawei','1C8E5C':'Huawei',
    '20F3A3':'Huawei','283152':'Huawei','2C58E8':'Huawei','30D17E':'Huawei','3431C4':'Huawei',
    '386BBB':'Huawei','3C467D':'Huawei','40CBA8':'Huawei','485F99':'Huawei','4C5499':'Huawei',
    '4CB16C':'Huawei','5489C2':'Huawei','5CB395':'Huawei','60DE44':'Huawei','64A651':'Huawei',
    '70723C':'Huawei','7826BC':'Huawei','7C1CF1':'Huawei','7C7D3D':'Huawei','842B2B':'Huawei',
    '88CEFA':'Huawei','8CDCD4':'Huawei','9070FF':'Huawei','94047B':'Huawei','9C28BF':'Huawei',
    'A02B5C':'Huawei','A4DFB6':'Huawei','A8993C':'Huawei','ACE215':'Huawei','B0E5ED':'Huawei',
    'B41C30':'Huawei','BCE143':'Huawei','C002C5':'Huawei','C8141B':'Huawei','D02DB3':'Huawei',
    'D8490B':'Huawei','DCD2FC':'Huawei','E091F5':'Huawei','E832B0':'Huawei','EC388F':'Huawei',
    'F4DCF9':'Huawei','F83D4E':'Huawei','FCB5DA':'Huawei',
    // H3C / 新华三
    '000FE2':'H3C','000F8F':'H3C','00237D':'H3C','002389':'H3C','002F5F':'H3C','08F6F7':'H3C',
    '0CDA41':'H3C','105F49':'H3C','1C3DE7':'H3C','38EAA7':'H3C','5067F0':'H3C','58696F':'H3C',
    '74EAC8':'H3C','881D79':'H3C','98F428':'H3C','A4B196':'H3C','BC7470':'H3C','D07AB5':'H3C',
    'EC8EB5':'H3C','F4E4AD':'H3C','FCB5DA':'H3C',
    // Cisco
    '000142':'Cisco','000163':'Cisco','000164':'Cisco','000196':'Cisco','000197':'Cisco',
    '0001C7':'Cisco','0001C9':'Cisco','000216':'Cisco','000217':'Cisco','00024A':'Cisco',
    '00024B':'Cisco','000295':'Cisco','000A41':'Cisco','000A42':'Cisco','000A8A':'Cisco',
    '000B45':'Cisco','000B46':'Cisco','000B5F':'Cisco','000B60':'Cisco','000BBE':'Cisco',
    '000BBF':'Cisco','000C30':'Cisco','000C31':'Cisco','000CCE':'Cisco','000CCF':'Cisco',
    '000D28':'Cisco','000D29':'Cisco','000D63':'Cisco','000D65':'Cisco','000DBC':'Cisco',
    '000DBD':'Cisco','000DEC':'Cisco','000DED':'Cisco','000E08':'Cisco','000E0C':'Cisco',
    '000E38':'Cisco','000E39':'Cisco','000E83':'Cisco','000E84':'Cisco','000ED6':'Cisco',
    '000ED7':'Cisco','000F23':'Cisco','000F24':'Cisco','000F34':'Cisco','000F35':'Cisco',
    '000F8F':'Cisco','000F90':'Cisco','000FF7':'Cisco','000FF8':'Cisco','001007':'Cisco',
    '001011':'Cisco','001029':'Cisco','00102F':'Cisco','001054':'Cisco','00107B':'Cisco',
    '0010F6':'Cisco','0010FF':'Cisco','001101':'Cisco','001120':'Cisco','001121':'Cisco',
    '00115C':'Cisco','00115D':'Cisco','001192':'Cisco','001193':'Cisco','0011BB':'Cisco',
    '0011BC':'Cisco','002016':'Cisco','002017':'Cisco','000ED7':'Cisco',
    // 锐捷 / Ruijie
    '00D0F8':'Ruijie','004C7F':'Ruijie','009173':'Ruijie','0CFC83':'Ruijie','30A8DB':'Ruijie',
    '5869FE':'Ruijie','782DAD':'Ruijie','8C16C9':'Ruijie','C04A00':'Ruijie','EC22BA':'Ruijie',
    'F4FE36':'Ruijie',
    // Juniper
    '000585':'Juniper','000F7C':'Juniper','000FE3':'Juniper','001059':'Juniper','002283':'Juniper',
    '0026F1':'Juniper','002A72':'Juniper','002A77':'Juniper','002A95':'Juniper','002CAB':'Juniper',
    '0040DD':'Juniper','0040E0':'Juniper','0050E4':'Juniper','005056':'Juniper','008051':'Juniper',
    '00A079':'Juniper','087A4C':'Juniper','0C81A4':'Juniper','0C8636':'Juniper','148FC6':'Juniper',
    '1C0E2C':'Juniper','2C2197':'Juniper','2C6BF5':'Juniper','40A677':'Juniper','40B4F0':'Juniper',
    '4C16FC':'Juniper','5C5EAB':'Juniper','78198B':'Juniper','78FE3D':'Juniper','7CE2CA':'Juniper',
    'AC4BC8':'Juniper','B0A86E':'Juniper','C4FE5C':'Juniper','D4ECBB':'Juniper','EC3EF7':'Juniper',
    'F0E50A':'Juniper','F4B52F':'Juniper',
    // Aruba (HPE)
    '000B86':'Aruba','001A1E':'Aruba','002475':'Aruba','24DEC6':'Aruba','40E3D6':'Aruba',
    '6CF37F':'Aruba','94B40F':'Aruba','9C1C12':'Aruba','D8C7C8':'Aruba','F09FC2':'Aruba',
    // Dell
    '0014FE':'Dell','005056':'Dell','00188B':'Dell','002219':'Dell','00219B':'Dell','002564':'Dell',
    '00B0D0':'Dell','00C09F':'Dell','185A58':'Dell','246E96':'Dell','2C600C':'Dell','3417EB':'Dell',
    '34E6D7':'Dell','509A4C':'Dell','54482E':'Dell','5CF9DD':'Dell','782BCB':'Dell','98404E':'Dell',
    'B083FE':'Dell','B8AC6F':'Dell','BC305B':'Dell','C81F66':'Dell','D481D7':'Dell','D4AE52':'Dell',
    'D4BED9':'Dell','D67E0E':'Dell','D89EF3':'Dell','E4434B':'Dell','F8B156':'Dell','F8BC12':'Dell',
    'F8DB88':'Dell',
    // HP / HPE
    '00306E':'HP','001A4B':'HP','001CC4':'HP','001E0B':'HP','002264':'HP','0023AE':'HP','0024A8':'HP',
    '0025B3':'HP','002655':'HP','0026F1':'HP','0030C1':'HP','008064':'HP','009C02':'HP','08002B':'HP',
    '101F74':'HP','105F49':'HP','14582D':'HP','185635':'HP','1C98EC':'HP','1CC1DE':'HP','24BE05':'HP',
    '28924A':'HP','2C2615':'HP','2C414F':'HP','2C4138':'HP','2C44FD':'HP','2C59E5':'HP','2C7676':'HP',
    '305A3A':'HP','30E171':'HP','3464A9':'HP','3897D6':'HP','38EAA7':'HP','40A8F0':'HP','40B0E8':'HP',
    '441319':'HP','5065F3':'HP','60E32A':'HP','64514B':'HP','646BD3':'HP','6CC217':'HP','78E3B5':'HP',
    '8030DC':'HP','9457A5':'HP','94EBCD':'HP','98E7F5':'HP','9CDC71':'HP','9CE19F':'HP','A0481C':'HP',
    'AC162D':'HP','B0BD6E':'HP','B499BA':'HP','C8B5AD':'HP','C8CBB8':'HP','C8D3FF':'HP','D8D385':'HP',
    'EC9A74':'HP','EC8EB5':'HP','F02FA8':'HP','F0921C':'HP','F4CE46':'HP',
    // Apple
    '003065':'Apple','000A27':'Apple','000A95':'Apple','000D93':'Apple','0011D9':'Apple','0011F5':'Apple',
    '0014F1':'Apple','0016CB':'Apple','0017F2':'Apple','0019E3':'Apple','001B63':'Apple','001CB3':'Apple',
    '001D4F':'Apple','001E52':'Apple','001EC2':'Apple','001F5B':'Apple','001FF3':'Apple','002241':'Apple',
    '002332':'Apple','00236C':'Apple','0023DF':'Apple','002500':'Apple','00254B':'Apple','0025BC':'Apple',
    '002608':'Apple','00264A':'Apple','0026B0':'Apple','0026BB':'Apple','004826':'Apple','0050E4':'Apple',
    '040CCE':'Apple','041552':'Apple','044BED':'Apple','047D7B':'Apple','04DB56':'Apple','04E536':'Apple',
    '04F13E':'Apple','04F7E4':'Apple','080007':'Apple','085AE0':'Apple','0C3021':'Apple','0C4DE9':'Apple',
    // Intel
    '001302':'Intel','001517':'Intel','0019D1':'Intel','001B21':'Intel','001CC0':'Intel','001E64':'Intel',
    '001E65':'Intel','001E67':'Intel','002170':'Intel','00216A':'Intel','00216B':'Intel','002268':'Intel',
    '002269':'Intel','00241D':'Intel','00248C':'Intel','002618':'Intel','0026C6':'Intel','0026C7':'Intel',
    '00A0C9':'Intel','08118A':'Intel','0C8BFD':'Intel','0CD292':'Intel','100BA9':'Intel','144F8A':'Intel',
    '20167A':'Intel','24770D':'Intel','246E96':'Intel','28C2DD':'Intel','3CFDFE':'Intel','405BD8':'Intel',
    '4848BF':'Intel','4C800F':'Intel','5CE0C5':'Intel','606720':'Intel','6CB0CE':'Intel','7470FD':'Intel',
    '7CB27D':'Intel','886B6E':'Intel','8C0414':'Intel','8C1645':'Intel','8C705A':'Intel','94659C':'Intel',
    'A0A8CD':'Intel','A0C589':'Intel','C0BFC0':'Intel','D0577B':'Intel','D896E0':'Intel','E84E06':'Intel',
    // 中兴 ZTE
    '00193E':'ZTE','002293':'ZTE','002615':'ZTE','002643':'ZTE','0026ED':'ZTE','08181A':'ZTE',
    '083FBC':'ZTE','100833':'ZTE','246183':'ZTE','3473DF':'ZTE','4C16F1':'ZTE','5063A2':'ZTE',
    '5887E7':'ZTE','78AC44':'ZTE','7889E8':'ZTE','7C111B':'ZTE','D0608C':'ZTE','D45D42':'ZTE',
    'EC237B':'ZTE','F4B72F':'ZTE','F46DE2':'ZTE','FCC897':'ZTE',
    // VMware
    '000C29':'VMware','000569':'VMware','001C14':'VMware','005056':'VMware','504208':'VMware',
    // 山石 Hillstone
    '00C0DF':'Hillstone',
    // 深信服 Sangfor
    'F4B5AA':'Sangfor','9009D0':'Sangfor',
    // 启明星辰 Venustech
    '0050BA':'Venustech',
    // 网神 LeadSec
    '0050BA':'LeadSec',
    // Fortinet
    '00090F':'Fortinet','04D590':'Fortinet','08816F':'Fortinet','088115':'Fortinet','0C9EBA':'Fortinet',
    '70684A':'Fortinet','90176B':'Fortinet','A4F4C2':'Fortinet','E83135':'Fortinet','F0A77E':'Fortinet',
    // PaloAlto
    '00134B':'PaloAlto','000D5A':'PaloAlto','000DBA':'PaloAlto','708BCD':'PaloAlto','B4A9FC':'PaloAlto',
    // Maipu 迈普
    '001F1E':'Maipu','08577C':'Maipu','D85DFB':'Maipu',
    // TP-Link
    'E894F6':'TP-Link','000A78':'TP-Link','002127':'TP-Link','0025F1':'TP-Link','64668A':'TP-Link',
    // 普通 OUI 别名
    '525400':'QEMU/KVM','080027':'VirtualBox','000C29':'VMware','001C42':'Parallels',
};

function convertMAC() {
    const input = document.getElementById('macInput').value.trim();
    if (!input) { showToast('请输入 MAC', 'info'); return; }
    const mac = input.replace(/[^a-fA-F0-9]/g, '').toUpperCase();
    if (mac.length !== 12) { showToast('MAC 应为 12 个十六进制字符', 'warning'); return; }
    const formats = {
        '冒号分隔': mac.match(/.{2}/g).join(':'),
        '横线分隔': mac.match(/.{2}/g).join('-'),
        '点分隔(思科)': mac.match(/.{4}/g).join('.').toLowerCase(),
        '无分隔': mac,
        '小写冒号': mac.match(/.{2}/g).join(':').toLowerCase(),
        'OUI (前24位)': mac.substring(0, 6),
    };
    // 单播/组播/本地 标识
    const firstByte = parseInt(mac.substring(0, 2), 16);
    const isMulticast = (firstByte & 1) === 1;
    const isLocal = (firstByte & 2) === 2;
    const flagBadges = [
        isMulticast ? '<span class="badge bg-warning">组播/广播</span>' : '<span class="badge bg-success">单播</span>',
        isLocal ? '<span class="badge bg-info">本地管理(LAA)</span>' : '<span class="badge bg-secondary">全球唯一(IEEE分配)</span>',
    ].join(' ');

    document.getElementById('macResult').style.display = 'block';
    document.getElementById('macResult').innerHTML = `
        <div class="card mb-2"><div class="card-header py-2"><strong>格式转换</strong> ${flagBadges}</div>
            <table class="table table-sm mb-0">
                ${Object.entries(formats).map(([k,v]) => `<tr><th width="140">${k}</th><td><code>${v}</code> <button class="btn btn-sm btn-outline-secondary py-0 px-2 ms-1" onclick="copyText('${v}')"><i class="bi-clipboard"></i></button></td></tr>`).join('')}
            </table>
        </div>`;
}

function lookupVendor() {
    const input = document.getElementById('macInput').value.trim();
    if (!input) { showToast('请输入 MAC', 'info'); return; }
    const mac = input.replace(/[^a-fA-F0-9]/g, '').toUpperCase();
    if (mac.length < 6) { showToast('至少需要前 6 位（OUI）', 'warning'); return; }
    const oui = mac.substring(0, 6);
    const vendor = OUI_DB[oui];
    document.getElementById('vendorResult').style.display = 'block';
    if (vendor) {
        document.getElementById('vendorResult').innerHTML = `
            <div class="card border-success">
                <div class="card-body">
                    <h5 class="text-success mb-2"><i class="bi-check-circle"></i> 查询结果</h5>
                    <table class="table table-sm mb-0">
                        <tr><th width="120">OUI 前缀</th><td><code>${oui}</code></td></tr>
                        <tr><th>厂商名称</th><td><strong class="fs-5">${vendor}</strong></td></tr>
                        <tr><th>OUI 数据源</th><td><small class="text-muted">内置常见厂商库（约 ${Object.keys(OUI_DB).length} 条）</small></td></tr>
                    </table>
                </div>
            </div>`;
    } else {
        document.getElementById('vendorResult').innerHTML = `
            <div class="card border-warning">
                <div class="card-body">
                    <h5 class="text-warning mb-2"><i class="bi-question-circle"></i> 未匹配到内置厂商</h5>
                    <p class="mb-1">OUI 前缀 <code>${oui}</code> 不在内置数据库中。</p>
                    <p class="mb-0 small text-muted">请访问 <a href="http://standards-oui.ieee.org/oui/oui.txt" target="_blank">IEEE 官方 OUI 数据库</a>
                       或 <a href="https://maclookup.app/search/result?mac=${oui}" target="_blank">MacLookup</a> 进行在线查询。</p>
                </div>
            </div>`;
    }
}

// ============================ 进制转换 ============================
function convertRadix() {
    const input = document.getElementById('radixInput').value.trim();
    const fromBase = parseInt(document.getElementById('radixFrom').value);
    if (!input) {
        ['radixBin','radixOct','radixDec','radixHex'].forEach(id => document.getElementById(id).textContent = '-');
        return;
    }
    try {
        const dec = parseInt(input, fromBase);
        if (isNaN(dec) || dec < 0) throw new Error('无效');
        let bin = dec.toString(2);
        bin = bin.padStart(Math.ceil(bin.length/8)*8, '0').match(/.{8}/g).join(' ');
        document.getElementById('radixBin').textContent = bin;
        document.getElementById('radixOct').textContent = dec.toString(8);
        document.getElementById('radixDec').textContent = dec.toLocaleString();
        document.getElementById('radixHex').textContent = '0x' + dec.toString(16).toUpperCase();
    } catch(e) {
        ['radixBin','radixOct','radixDec','radixHex'].forEach(id => document.getElementById(id).textContent = '错误');
    }
}

function convertIpBinary() {
    const ip = document.getElementById('radixIpInput').value.trim();
    const parts = ip.split('.');
    if (parts.length !== 4 || !parts.every(p => /^\d+$/.test(p) && +p >= 0 && +p <= 255)) {
        ['ipBinary','ipDecimal','ipHex','ipWildcard'].forEach(id => document.getElementById(id).textContent = '-');
        return;
    }
    const oct = parts.map(Number);
    document.getElementById('ipBinary').textContent = oct.map(o => o.toString(2).padStart(8, '0')).join('.');
    document.getElementById('ipDecimal').textContent = (((oct[0]<<24)|(oct[1]<<16)|(oct[2]<<8)|oct[3])>>>0).toString();
    document.getElementById('ipHex').textContent = '0x' + oct.map(o => o.toString(16).padStart(2, '0').toUpperCase()).join('');
    document.getElementById('ipWildcard').textContent = oct.map(o => 255-o).join('.');
}

// ============================ 时间戳 ============================
function convertTimestamp() {
    const ts = document.getElementById('tsInput').value.trim();
    const dt = document.getElementById('dtInput').value;
    let date = null;
    if (ts) {
        let n = parseInt(ts);
        if (isNaN(n)) { showToast('无效时间戳', 'warning'); return; }
        if (n < 1e12) n *= 1000;  // 秒 → 毫秒
        date = new Date(n);
    } else if (dt) {
        date = new Date(dt);
    } else { showToast('请输入时间戳或日期', 'info'); return; }
    const sec = Math.floor(date.getTime() / 1000);
    const ms = date.getTime();
    const iso = date.toISOString();
    const local = date.toLocaleString('zh-CN', {hour12: false});
    const utc = date.toUTCString();
    document.getElementById('tsResult').style.display = 'block';
    document.getElementById('tsResult').innerHTML = `<table class="table table-sm">
        <tr><th width="160">Unix 时间戳 (秒)</th><td><code>${sec}</code> <button class="btn btn-sm btn-outline-secondary ms-1" onclick="copyText('${sec}')"><i class="bi-clipboard"></i></button></td></tr>
        <tr><th>Unix 时间戳 (毫秒)</th><td><code>${ms}</code></td></tr>
        <tr><th>本地时间</th><td>${local}</td></tr>
        <tr><th>ISO 8601 (UTC)</th><td><code>${iso}</code></td></tr>
        <tr><th>UTC 字符串</th><td>${utc}</td></tr>
    </table>`;
}

// ============================ Base64 ============================
function encodeBase64() {
    const input = document.getElementById('b64Input').value;
    try {
        const bytes = new TextEncoder().encode(input);
        const bstr = String.fromCharCode(...bytes);
        document.getElementById('b64Output').value = btoa(bstr);
    } catch(e) { showToast('编码失败: ' + e.message, 'danger'); }
}
function decodeBase64() {
    const input = document.getElementById('b64Input').value.trim();
    try {
        const bstr = atob(input);
        const bytes = new Uint8Array(bstr.length);
        for (let i = 0; i < bstr.length; i++) bytes[i] = bstr.charCodeAt(i);
        document.getElementById('b64Output').value = new TextDecoder().decode(bytes);
    } catch(e) { showToast('解码失败: ' + e.message, 'danger'); }
}
function hexToBase64() {
    const hex = document.getElementById('b64Input').value.replace(/\s|0x/gi, '');
    if (!/^[0-9a-fA-F]*$/.test(hex) || hex.length % 2) { showToast('无效 HEX', 'warning'); return; }
    let bstr = '';
    for (let i = 0; i < hex.length; i += 2) bstr += String.fromCharCode(parseInt(hex.substr(i, 2), 16));
    document.getElementById('b64Output').value = btoa(bstr);
}
function base64ToHex() {
    try {
        const bstr = atob(document.getElementById('b64Input').value.trim());
        let hex = '';
        for (let i = 0; i < bstr.length; i++) hex += bstr.charCodeAt(i).toString(16).padStart(2, '0');
        document.getElementById('b64Output').value = hex.toUpperCase();
    } catch(e) { showToast('转换失败', 'danger'); }
}

// ============================ MTU 计算器 ============================
function calcMtuAdvanced() {
    const base = parseInt(document.getElementById('mtuBase').value) || 1500;
    let overhead = 0;
    const layers = [];
    if (document.getElementById('mtu_dot1q').checked) { overhead += 4; layers.push('802.1Q (+4)'); }
    if (document.getElementById('mtu_qinq').checked) { overhead += 8; layers.push('QinQ (+8)'); }
    if (document.getElementById('mtu_mpls1').checked) { overhead += 4; layers.push('MPLS×1 (+4)'); }
    if (document.getElementById('mtu_mpls2').checked) { overhead += 8; layers.push('MPLS×2 (+8)'); }
    if (document.getElementById('mtu_pppoe').checked) { overhead += 8; layers.push('PPPoE (+8)'); }
    if (document.getElementById('mtu_gre').checked) { overhead += 24; layers.push('GRE (+24)'); }
    if (document.getElementById('mtu_ipsec').checked) { overhead += 73; layers.push('IPsec ESP (+73 max)'); }
    if (document.getElementById('mtu_vxlan').checked) { overhead += 50; layers.push('VxLAN (+50)'); }
    const effective = base - overhead;
    const ipMTU = effective;
    const tcpMSS = effective - 40;  // IP 20 + TCP 20
    document.getElementById('mtuResult').innerHTML = `<table class="table table-sm">
        <tr><th width="180">底层 MTU</th><td><code>${base}</code> 字节</td></tr>
        <tr><th>叠加封装总开销</th><td><code>${overhead}</code> 字节 ${layers.length ? '<small class="text-muted">('+layers.join(', ')+')</small>' : ''}</td></tr>
        <tr><th>有效净载 (IP MTU)</th><td><strong class="text-${ipMTU < 1280 ? 'danger':'success'}">${ipMTU}</strong> 字节</td></tr>
        <tr><th>TCP MSS (推荐)</th><td><code>${tcpMSS}</code> 字节 <small class="text-muted">(IP MTU - 40)</small></td></tr>
    </table>${ipMTU < 1280 ? '<div class="alert alert-warning mt-2">IPv6 最小 MTU 为 1280，当前小于该值，IPv6 将无法工作。</div>' : ''}`;
}

// ============================ 带宽计算器 ============================
function bytesIn(unit) {
    return {KB: 1024, MB: 1024**2, GB: 1024**3, TB: 1024**4}[unit] || 1;
}
function bpsIn(unit) {
    return {bps: 1, Kbps: 1e3, Mbps: 1e6, Gbps: 1e9}[unit] || 1;
}
function fmtTime(s) {
    if (s < 60) return s.toFixed(2) + ' 秒';
    if (s < 3600) return (s/60).toFixed(2) + ' 分';
    if (s < 86400) return (s/3600).toFixed(2) + ' 小时';
    return (s/86400).toFixed(2) + ' 天';
}
function fmtSpeed(bps) {
    if (bps < 1e3) return bps.toFixed(2) + ' bps';
    if (bps < 1e6) return (bps/1e3).toFixed(2) + ' Kbps';
    if (bps < 1e9) return (bps/1e6).toFixed(2) + ' Mbps';
    return (bps/1e9).toFixed(2) + ' Gbps';
}

function calcTransferTime() {
    const size = parseFloat(document.getElementById('bw_t_size').value) * bytesIn(document.getElementById('bw_t_size_unit').value);
    const bw = parseFloat(document.getElementById('bw_t_bw').value) * bpsIn(document.getElementById('bw_t_bw_unit').value);
    if (!size || !bw) { showToast('请输入有效数值', 'warning'); return; }
    const bits = size * 8;
    const ideal = bits / bw;
    const real = ideal / 0.7;  // 70% 利用率
    document.getElementById('bw_t_result').innerHTML = `<div class="alert alert-success">
        理想时间（100% 利用率）：<strong>${fmtTime(ideal)}</strong><br>
        实际预估（按 70% 利用率）：<strong>${fmtTime(real)}</strong>
    </div>`;
}

function calcRequiredBandwidth() {
    const size = parseFloat(document.getElementById('bw_n_size').value) * bytesIn(document.getElementById('bw_n_size_unit').value);
    const time = parseFloat(document.getElementById('bw_n_time').value);
    if (!size || !time) { showToast('请输入有效数值', 'warning'); return; }
    const bps = (size * 8) / time;
    const withOverhead = bps / 0.7;
    document.getElementById('bw_n_result').innerHTML = `<div class="alert alert-success">
        最低带宽（理论）：<strong>${fmtSpeed(bps)}</strong><br>
        建议带宽（含 30% 冗余）：<strong>${fmtSpeed(withOverhead)}</strong>
    </div>`;
}

function calcConcurrentBandwidth() {
    const users = parseInt(document.getElementById('bw_c_users').value);
    const per = parseFloat(document.getElementById('bw_c_per').value) * 1000;  // Kbps -> bps
    const peak = parseFloat(document.getElementById('bw_c_peak').value);
    if (!users || !per || !peak) { showToast('请输入有效数值', 'warning'); return; }
    const avg = users * per;
    const peakBps = avg * peak;
    document.getElementById('bw_c_result').innerHTML = `<div class="alert alert-success">
        平均总带宽：<strong>${fmtSpeed(avg)}</strong><br>
        峰值总带宽：<strong>${fmtSpeed(peakBps)}</strong> <small class="text-muted">(× ${peak} 峰值系数)</small>
    </div>`;
}

// ============================ 报文分析 ============================
function fmtMac(b, off) {
    return [b[off],b[off+1],b[off+2],b[off+3],b[off+4],b[off+5]].map(x=>x.toString(16).padStart(2,'0')).join(':');
}
function fmtIp4(b, off) {
    return `${b[off]}.${b[off+1]}.${b[off+2]}.${b[off+3]}`;
}

function loadPacketSample(s) {
    // 切到粘贴模式
    const r = document.getElementById('pkt_mode_paste');
    if (r) { r.checked = true; if (typeof pktApplyMode === 'function') pktApplyMode(); }
    document.getElementById('pkt_data').value = s;
    document.getElementById('pkt_fmt').value = 'hex';
    pktDoParse();
}

function parseHexBytes(s) {
    s = s.replace(/[\s:.\-]+/g, '').replace(/0x/gi, '');
    if (!/^[0-9a-fA-F]*$/.test(s) || s.length % 2) throw new Error('无效 HEX 字符串');
    const bytes = new Uint8Array(s.length / 2);
    for (let i = 0; i < s.length; i += 2) bytes[i/2] = parseInt(s.substr(i, 2), 16);
    return bytes;
}
function parseB64Bytes(s) {
    const bstr = atob(s.replace(/\s/g, ''));
    const bytes = new Uint8Array(bstr.length);
    for (let i = 0; i < bstr.length; i++) bytes[i] = bstr.charCodeAt(i);
    return bytes;
}

// PCAP 文件解析：返回所有帧 [{ts, bytes}, ...]
// PCAP 全局头 24 字节：magic(4) + version(2+2) + thiszone(4) + sigfigs(4) + snaplen(4) + linktype(4)
// 每个包前 16 字节包头：ts_sec(4) + ts_usec(4) + incl_len(4) + orig_len(4)
function parsePcapAllFrames(bytes) {
    if (bytes.length < 24 + 16) throw new Error('PCAP 文件长度不足');
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const magic = dv.getUint32(0, false);
    let littleEndian, nanoTs = false;
    if (magic === 0xa1b2c3d4) { littleEndian = false; nanoTs = false; }
    else if (magic === 0xa1b23c4d) { littleEndian = false; nanoTs = true; }
    else if (magic === 0xd4c3b2a1) { littleEndian = true; nanoTs = false; }
    else if (magic === 0x4d3cb2a1) { littleEndian = true; nanoTs = true; }
    else throw new Error('非 PCAP 格式（魔数: 0x' + magic.toString(16) + '）');
    const linktype = dv.getUint32(20, littleEndian);
    if (linktype !== 1) {
        throw new Error('暂只支持以太网 (LINKTYPE_ETHERNET=1)，当前 linktype=' + linktype);
    }
    const frames = [];
    let off = 24;
    while (off + 16 <= bytes.length && frames.length < 5000) {
        const tsSec = dv.getUint32(off, littleEndian);
        const tsFrac = dv.getUint32(off + 4, littleEndian);
        const inclLen = dv.getUint32(off + 8, littleEndian);
        if (inclLen <= 0 || inclLen > 65535) break;
        if (off + 16 + inclLen > bytes.length) break;
        const ts = tsSec + tsFrac / (nanoTs ? 1e9 : 1e6);
        frames.push({
            ts: ts,
            bytes: bytes.slice(off + 16, off + 16 + inclLen),
        });
        off += 16 + inclLen;
    }
    return {
        frames: frames,
        info: 'PCAP (' + (littleEndian ? 'LE' : 'BE') + (nanoTs ? ', nano-ts' : '') + ', linktype=Ethernet, ' + frames.length + ' 帧)',
    };
}

// PCAPNG 简化解析：扫描所有 EPB(Enhanced Packet Block, 0x06) 和 SPB(0x03)
function parsePcapngAllFrames(bytes) {
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (bytes.length < 12) throw new Error('PCAPNG 文件长度不足');
    if (dv.getUint32(0, false) !== 0x0a0d0d0a) throw new Error('非 PCAPNG 格式');
    const bom = dv.getUint32(8, false);
    const littleEndian = (bom === 0x4d3c2b1a);
    const frames = [];
    let off = dv.getUint32(4, littleEndian);  // SHB total_len
    let tsResolution = 1e6;  // 默认微秒分辨率（PCAPNG IDB if_tsresol option）
    while (off + 8 <= bytes.length && frames.length < 5000) {
        const blockType = dv.getUint32(off, littleEndian);
        const blockLen = dv.getUint32(off + 4, littleEndian);
        if (blockLen < 12 || off + blockLen > bytes.length) break;
        if (blockType === 0x00000006) {
            // EPB
            const tsHigh = dv.getUint32(off + 12, littleEndian);
            const tsLow = dv.getUint32(off + 16, littleEndian);
            const capLen = dv.getUint32(off + 20, littleEndian);
            const dataStart = off + 28;
            const ts64 = (tsHigh * 0x100000000 + tsLow) / tsResolution;
            frames.push({ts: ts64, bytes: bytes.slice(dataStart, dataStart + capLen)});
        } else if (blockType === 0x00000003) {
            // SPB
            const origLen = dv.getUint32(off + 8, littleEndian);
            const cap = Math.min(origLen, blockLen - 16);
            frames.push({ts: 0, bytes: bytes.slice(off + 12, off + 12 + cap)});
        }
        off += blockLen;
    }
    return {
        frames: frames,
        info: 'PCAPNG (' + (littleEndian ? 'LE' : 'BE') + ', ' + frames.length + ' 帧)',
    };
}

// 兼容旧调用
function parsePcapFirstFrame(bytes) {
    const r = parsePcapAllFrames(bytes);
    if (!r.frames.length) throw new Error('PCAP 文件中没有数据包');
    return { frame: r.frames[0].bytes, info: r.info };
}
function parsePcapngFirstFrame(bytes) {
    const r = parsePcapngAllFrames(bytes);
    if (!r.frames.length) throw new Error('PCAPNG 中未找到包数据块 (EPB/SPB)');
    return { frame: r.frames[0].bytes, info: r.info };
}

// ============================ 新版统一管线 ============================
// 全局状态（一次性归一化，所有视图共享）
const pktState = {
    frames: [],            // 规范化 Record[]
    sessions: [],          // 派生 Session[]
    view: 'frames-all',
    filter: { ip: '', port: '', app: '' },
    geoCache: new Map(),   // ip -> { country, province, city, label }
    geoPending: false,
    sourceInfo: '',
    selectedIdx: -1,
};

// ---- 模式切换 (粘贴 / 文件) ----
function pktApplyMode() {
    const mode = document.querySelector('input[name="pkt_mode"]:checked')?.value || 'file';
    document.querySelectorAll('.pkt-paste-only').forEach(el => el.style.display = (mode === 'paste' ? '' : 'none'));
    document.querySelectorAll('.pkt-file-only').forEach(el => el.style.display = (mode === 'file' ? '' : 'none'));
}

// ---- 解析入口 ----
async function pktDoParse() {
    const mode = document.querySelector('input[name="pkt_mode"]:checked')?.value || 'file';
    try {
        if (mode === 'paste') {
            const fmt = document.getElementById('pkt_fmt').value;
            const data = document.getElementById('pkt_data').value.trim();
            if (!data) { showToast('请输入报文数据', 'info'); return; }
            const bytes = fmt === 'hex' ? parseHexBytes(data) : parseB64Bytes(data);
            loadFrames([{ ts: 0, bytes: bytes }], `粘贴 (${bytes.length} 字节)`);
        } else {
            const fileInput = document.getElementById('pkt_file');
            const file = fileInput.files[0];
            if (!file) { showToast('请选择文件', 'info'); return; }
            const ext = (file.name.split('.').pop() || '').toLowerCase();
            const ab = await file.arrayBuffer();
            const u8 = new Uint8Array(ab);
            let rawFrames, info;
            if (ext === 'pcap' || ext === 'cap') {
                const r = parsePcapAllFrames(u8); rawFrames = r.frames; info = file.name + ' → ' + r.info;
            } else if (ext === 'pcapng') {
                const r = parsePcapngAllFrames(u8); rawFrames = r.frames; info = file.name + ' → ' + r.info;
            } else if (ext === 'txt' || ext === 'hex' || ext === 'dump') {
                const text = await file.text();
                const bytes = parseHexBytes(text);
                rawFrames = [{ ts: 0, bytes: bytes }];
                info = file.name + ' (HEX 文本, ' + bytes.length + ' 字节)';
            } else if (ext === 'bin') {
                rawFrames = [{ ts: 0, bytes: u8 }];
                info = file.name + ' (原始字节, ' + u8.length + ' 字节)';
            } else {
                // 自动识别魔数
                if (u8.length >= 4) {
                    const m = (u8[0] << 24 | u8[1] << 16 | u8[2] << 8 | u8[3]) >>> 0;
                    if (m === 0xa1b2c3d4 || m === 0xd4c3b2a1 || m === 0xa1b23c4d || m === 0x4d3cb2a1) {
                        const r = parsePcapAllFrames(u8); rawFrames = r.frames; info = file.name + ' → ' + r.info;
                    } else if (m === 0x0a0d0d0a) {
                        const r = parsePcapngAllFrames(u8); rawFrames = r.frames; info = file.name + ' → ' + r.info;
                    } else {
                        rawFrames = [{ ts: 0, bytes: u8 }];
                        info = file.name + ' (自动识别为原始字节)';
                    }
                } else { throw new Error('文件过小'); }
            }
            loadFrames(rawFrames, info);
        }
    } catch (e) {
        showToast('解析失败: ' + (e && e.message ? e.message : e), 'danger');
    }
}

function pktDoReset() {
    pktState.frames = []; pktState.sessions = []; pktState.geoCache.clear();
    pktState.view = 'frames-all'; pktState.filter = { ip: '', port: '', app: '' };
    pktState.sourceInfo = ''; pktState.selectedIdx = -1;
    document.getElementById('pkt_data').value = '';
    const f = document.getElementById('pkt_file'); if (f) f.value = '';
    document.getElementById('flt_ip').value = '';
    document.getElementById('flt_port').value = '';
    document.getElementById('flt_app').value = '';
    document.getElementById('pkt_detail').innerHTML = '';
    document.getElementById('pkt_result').innerHTML = '';
    document.getElementById('pkt_source_info').textContent = '';
    document.getElementById('flt_count').textContent = '未加载数据';
    document.querySelectorAll('#pkt_sidebar .pkt-nav').forEach(li => li.classList.toggle('active', li.dataset.view === 'frames-all'));
    document.getElementById('pkt_thead').innerHTML = '';
    document.getElementById('pkt_tbody').innerHTML = '<tr><td class="text-center text-muted py-4">请先上传 PCAP 文件或粘贴报文数据后点击 "解析"</td></tr>';
    document.getElementById('pkt_view_title').textContent = '数据包列表';
    document.getElementById('pkt_view_meta').textContent = '';
}

// ---- 加载（一次性构建 Record/Session） ----
function loadFrames(rawFrames, sourceInfo) {
    if (!rawFrames || !rawFrames.length) {
        document.getElementById('pkt_result').innerHTML = '<div class="alert alert-warning">未识别到任何数据包</div>';
        return;
    }
    const tsBase = rawFrames[0].ts || 0;
    pktState.frames = rawFrames.map((f, i) => buildRecord(f.bytes, i, f.ts || 0, tsBase));
    pktState.sessions = buildSessions(pktState.frames);
    pktState.sourceInfo = sourceInfo;
    pktState.selectedIdx = -1;
    pktState.view = 'frames-all';
    document.querySelectorAll('#pkt_sidebar .pkt-nav').forEach(li => li.classList.toggle('active', li.dataset.view === 'frames-all'));
    document.getElementById('pkt_source_info').textContent = sourceInfo;
    document.getElementById('pkt_detail').innerHTML = '';
    document.getElementById('pkt_result').innerHTML = '';
    renderView();
    fetchGeo();  // 异步查询公网 IP 归属地，完成后再次 renderView
}

// ---- 构建单帧规范化记录 ----
function buildRecord(bytes, idx, ts, tsBase) {
    const rec = {
        idx: idx,
        ts: ts,
        relTs: ts > 0 ? (ts - tsBase) : 0,
        src: { ip: '', mac: '', port: null, label: '' },
        dst: { ip: '', mac: '', port: null, label: '' },
        l3: 'OTHER', l4: null, appProto: null, tlsVersion: null,
        domain: null, length: bytes.length, info: '', bytes: bytes, flags: null,
    };
    if (!bytes || bytes.length < 14) {
        rec.info = '长度不足'; return rec;
    }
    rec.src.mac = fmtMac(bytes, 6);
    rec.dst.mac = fmtMac(bytes, 0);
    const etherType = (bytes[12] << 8) | bytes[13];
    let off = 14;
    if (etherType === 0x0806) {
        // ARP
        rec.l3 = 'ARP';
        if (bytes.length >= off + 28) {
            const op = (bytes[off + 6] << 8) | bytes[off + 7];
            rec.src.ip = fmtIp4(bytes, off + 14);
            rec.dst.ip = fmtIp4(bytes, off + 24);
            rec.info = op === 1 ? `谁是 ${rec.dst.ip}？告诉 ${rec.src.ip}`
                : op === 2 ? `${rec.src.ip} 在 ${fmtMac(bytes, off + 8)}` : `ARP op=${op}`;
        }
    } else if (etherType === 0x0800 && bytes.length >= off + 20) {
        // IPv4
        rec.l3 = 'IPv4';
        const ihl = (bytes[off] & 0x0f) * 4;
        const proto = bytes[off + 9];
        rec.src.ip = fmtIp4(bytes, off + 12);
        rec.dst.ip = fmtIp4(bytes, off + 16);
        const l4 = off + ihl;
        if (proto === 6 && bytes.length >= l4 + 20) {
            rec.l4 = 'TCP';
            rec.src.port = (bytes[l4] << 8) | bytes[l4 + 1];
            rec.dst.port = (bytes[l4 + 2] << 8) | bytes[l4 + 3];
            const flags = bytes[l4 + 13];
            rec.flags = {
                syn: !!(flags & 0x02), ack: !!(flags & 0x10), fin: !!(flags & 0x01),
                rst: !!(flags & 0x04), psh: !!(flags & 0x08),
            };
            const fn = [];
            if (flags & 0x10) fn.push('ACK'); if (flags & 0x08) fn.push('PSH');
            if (flags & 0x04) fn.push('RST'); if (flags & 0x02) fn.push('SYN');
            if (flags & 0x01) fn.push('FIN');
            rec.info = `${rec.src.port} → ${rec.dst.port} [${fn.join(',') || '·'}]`;
            // TCP 载荷起点（用于 HTTP/TLS 提取）
            const dataOff = (bytes[l4 + 12] >> 4) * 4;
            rec._payloadOff = l4 + dataOff;
        } else if (proto === 17 && bytes.length >= l4 + 8) {
            rec.l4 = 'UDP';
            rec.src.port = (bytes[l4] << 8) | bytes[l4 + 1];
            rec.dst.port = (bytes[l4 + 2] << 8) | bytes[l4 + 3];
            rec.info = `${rec.src.port} → ${rec.dst.port}`;
            rec._payloadOff = l4 + 8;
        } else if (proto === 1 && bytes.length >= l4 + 4) {
            rec.l4 = 'ICMP';
            const t = bytes[l4], c = bytes[l4 + 1];
            const tn = ({ 0: '回显应答', 8: '回显请求', 3: '目的不可达', 11: '超时', 5: '重定向' })[t] || ('类型 ' + t);
            rec.info = `${tn} (code=${c})`;
        } else {
            rec.info = `IP proto=${proto}`;
        }
    } else if (etherType === 0x86dd) {
        rec.l3 = 'IPv6';
        if (bytes.length >= off + 40) {
            const nh = bytes[off + 6];
            rec.src.ip = fmtIp6(bytes, off + 8);
            rec.dst.ip = fmtIp6(bytes, off + 24);
            const l4 = off + 40;
            if (nh === 6 && bytes.length >= l4 + 20) {
                rec.l4 = 'TCP';
                rec.src.port = (bytes[l4] << 8) | bytes[l4 + 1];
                rec.dst.port = (bytes[l4 + 2] << 8) | bytes[l4 + 3];
                const dataOff = (bytes[l4 + 12] >> 4) * 4;
                rec._payloadOff = l4 + dataOff;
                rec.info = `${rec.src.port} → ${rec.dst.port}`;
            } else if (nh === 17 && bytes.length >= l4 + 8) {
                rec.l4 = 'UDP';
                rec.src.port = (bytes[l4] << 8) | bytes[l4 + 1];
                rec.dst.port = (bytes[l4 + 2] << 8) | bytes[l4 + 3];
                rec._payloadOff = l4 + 8;
                rec.info = `${rec.src.port} → ${rec.dst.port}`;
            } else if (nh === 58) {
                rec.l4 = 'ICMPv6';
                rec.info = 'ICMPv6';
            } else {
                rec.info = `IPv6 next=${nh}`;
            }
        }
    } else {
        rec.info = '以太网 0x' + etherType.toString(16);
    }
    // 应用层启发（端口）
    const sp = rec.src.port, dp = rec.dst.port;
    if (rec.l4 === 'UDP' && (sp === 53 || dp === 53)) rec.appProto = 'DNS';
    else if (rec.l4 === 'TCP' && (sp === 443 || dp === 443)) rec.appProto = 'TLS';
    else if (rec.l4 === 'TCP' && [80, 8080, 8000].some(p => p === sp || p === dp)) rec.appProto = 'HTTP';
    else if (rec.l4 === 'TCP' && (sp === 22 || dp === 22)) rec.appProto = 'SSH';
    // 应用层载荷提取
    extractAppLayer(rec);
    return rec;
}

function fmtIp6(b, off) {
    const parts = [];
    for (let i = 0; i < 16; i += 2) parts.push(((b[off + i] << 8) | b[off + i + 1]).toString(16));
    // 简单压缩 0
    return parts.join(':').replace(/(:0)+:/, '::').replace(/^0(::)/, '$1');
}

// ---- 应用层载荷提取（DNS QNAME / HTTP Host / TLS SNI） ----
function extractAppLayer(rec) {
    const off = rec._payloadOff;
    if (off == null || off >= rec.bytes.length) return;
    const b = rec.bytes;
    if (rec.appProto === 'DNS') {
        // DNS: 12 字节头，从 12 处开始读 QNAME（length-prefixed labels）
        const dnsStart = off;
        if (b.length < dnsStart + 13) return;
        const qdcount = (b[dnsStart + 4] << 8) | b[dnsStart + 5];
        if (qdcount < 1) return;
        let p = dnsStart + 12;
        const labels = [];
        let safety = 0;
        while (p < b.length && safety++ < 30) {
            const len = b[p];
            if (len === 0) break;
            if ((len & 0xc0) === 0xc0) break; // 压缩指针，QNAME 一般不压缩，遇到就停
            if (len > 63 || p + 1 + len > b.length) return;
            const lbl = []; for (let i = 0; i < len; i++) lbl.push(String.fromCharCode(b[p + 1 + i]));
            labels.push(lbl.join(''));
            p += 1 + len;
        }
        if (labels.length) {
            rec.domain = labels.join('.');
            rec.info = '查询 ' + rec.domain;
        }
    } else if (rec.appProto === 'HTTP') {
        // 前 1024 字节 ASCII 化
        const end = Math.min(b.length, off + 1024);
        if (end - off < 8) return;
        let s = '';
        for (let i = off; i < end; i++) {
            const c = b[i];
            s += (c >= 0x20 && c < 0x7f) || c === 0x0a || c === 0x0d ? String.fromCharCode(c) : ' ';
        }
        const m = s.match(/^(GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH|CONNECT|TRACE)\s+(\S+)\s+HTTP\/[\d.]+/m);
        if (m) rec.info = `${m[1]} ${m[2]}`;
        const h = s.match(/Host:\s*([^\r\n]+)/i);
        if (h) rec.domain = h[1].trim();
    } else if (rec.appProto === 'TLS') {
        // TLS Record: type(1) ver(2) len(2)，类型 22 = Handshake；HandshakeType 1 = ClientHello
        if (b.length < off + 5 + 4) return;
        if (b[off] !== 22) return;
        if (b[off + 5] !== 1) return;
        // 跳过 record(5) + handshake_header(4) + client_version(2) + random(32)
        let p = off + 5 + 4 + 2 + 32;
        if (p + 1 > b.length) return;
        const sidLen = b[p]; p += 1 + sidLen;
        if (p + 2 > b.length) return;
        const csLen = (b[p] << 8) | b[p + 1]; p += 2 + csLen;
        if (p + 1 > b.length) return;
        const cmLen = b[p]; p += 1 + cmLen;
        if (p + 2 > b.length) return;
        const extLen = (b[p] << 8) | b[p + 1]; p += 2;
        const extEnd = Math.min(b.length, p + extLen);
        let tlsVer = null;
        while (p + 4 <= extEnd) {
            const t = (b[p] << 8) | b[p + 1];
            const l = (b[p + 2] << 8) | b[p + 3];
            const v = p + 4;
            if (t === 0x0000 && v + 5 <= extEnd) {
                // server_name
                const snLen = (b[v + 3] << 8) | b[v + 4];
                if (v + 5 + snLen <= extEnd) {
                    let name = '';
                    for (let i = 0; i < snLen; i++) name += String.fromCharCode(b[v + 5 + i]);
                    rec.domain = name;
                }
            } else if (t === 0x002b) {
                // supported_versions: 客户端列出版本，挑最高
                const sv = b[v];
                let q = v + 1;
                while (q + 1 < v + 1 + sv) {
                    const ver = (b[q] << 8) | b[q + 1];
                    if (ver === 0x0304) tlsVer = 'TLSv1.3';
                    else if (ver === 0x0303 && !tlsVer) tlsVer = 'TLSv1.2';
                    q += 2;
                }
            }
            p = v + l;
        }
        if (!tlsVer) {
            // fallback：legacy_version
            const cv = (b[off + 5 + 4] << 8) | b[off + 5 + 4 + 1];
            if (cv === 0x0303) tlsVer = 'TLSv1.2';
            else if (cv === 0x0302) tlsVer = 'TLSv1.1';
        }
        rec.tlsVersion = tlsVer;
        if (rec.domain) rec.info = 'ClientHello SNI=' + rec.domain;
    } else if (rec.appProto === 'SSH') {
        // SSH-2.0-Banner...
        const end = Math.min(b.length, off + 64);
        let s = '';
        for (let i = off; i < end; i++) {
            const c = b[i];
            if (c === 0x0d || c === 0x0a) break;
            if (c >= 0x20 && c < 0x7f) s += String.fromCharCode(c);
        }
        if (s.startsWith('SSH-')) rec.info = s;
    }
}

// ---- 会话聚合 ----
function buildSessions(records) {
    const map = new Map();
    for (const r of records) {
        if (!r.l4 || (r.l4 !== 'TCP' && r.l4 !== 'UDP')) continue;
        if (r.src.port == null || r.dst.port == null) continue;
        const a = `${r.src.ip}|${r.src.port}`;
        const b = `${r.dst.ip}|${r.dst.port}`;
        const swap = a > b;
        const k1 = swap ? b : a, k2 = swap ? a : b;
        const key = `${r.l4}|${k1}|${k2}`;
        let s = map.get(key);
        if (!s) {
            const [ip1, p1] = k1.split('|'); const [ip2, p2] = k2.split('|');
            s = {
                idx: 0, l4: r.l4,
                ip1: ip1, port1: +p1, label1: '',
                ip2: ip2, port2: +p2, label2: '',
                appProto: null, tlsVersion: null, domain: null,
                tsStart: r.ts || 0, tsEnd: r.ts || 0,
                frames: 0, bytes: 0,
                firstRecIdx: r.idx,
            };
            map.set(key, s);
        }
        if (r.ts > 0) {
            if (!s.tsStart || r.ts < s.tsStart) s.tsStart = r.ts;
            if (r.ts > s.tsEnd) s.tsEnd = r.ts;
        }
        s.frames++;
        s.bytes += r.length;
        if (!s.appProto && r.appProto) s.appProto = r.appProto;
        if (!s.tlsVersion && r.tlsVersion) s.tlsVersion = r.tlsVersion;
        if (!s.domain && r.domain) s.domain = r.domain;
    }
    const arr = [...map.values()];
    arr.sort((a, b) => (a.tsStart - b.tsStart) || (a.firstRecIdx - b.firstRecIdx));
    arr.forEach((s, i) => {
        s.idx = i + 1;
        if (!s.appProto) {
            const lo = Math.min(s.port1, s.port2);
            s.appProto = ({ 53: 'DNS', 80: 'HTTP', 8080: 'HTTP', 8000: 'HTTP', 443: 'TLS', 22: 'SSH' })[lo] || s.l4;
        }
        s.duration = humanizeDuration(s.tsEnd - s.tsStart);
    });
    return arr;
}

function humanizeDuration(sec) {
    if (!isFinite(sec) || sec <= 0) return '0';
    if (sec < 1) return Math.round(sec * 1000) + '毫秒';
    if (sec < 60) {
        const ms = Math.round((sec % 1) * 1000);
        return Math.floor(sec) + '秒' + (ms ? ms + '毫秒' : '');
    }
    const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
    return m + '分钟' + (s ? s + '秒' : '');
}

// ---- 归属地查询 ----
function ipLocalLabel(ip) {
    if (!ip) return '';
    if (ip.indexOf(':') >= 0) {
        // IPv6 简化
        if (ip === '::1') return '回环';
        if (ip.startsWith('fe80')) return '链路本地';
        if (ip.startsWith('ff')) return '组播';
        if (/^(fc|fd)/.test(ip)) return '内网';
        return '';
    }
    const o = ip.split('.').map(Number);
    if (o.length !== 4 || o.some(x => isNaN(x))) return '';
    if (o[0] === 10) return '内网';
    if (o[0] === 127) return '回环';
    if (o[0] === 172 && o[1] >= 16 && o[1] <= 31) return '内网';
    if (o[0] === 192 && o[1] === 168) return '内网';
    if (o[0] === 169 && o[1] === 254) return '链路本地';
    if (o[0] >= 224 && o[0] <= 239) return '组播';
    if (o[0] === 255 && o[1] === 255 && o[2] === 255 && o[3] === 255) return '广播';
    return '';
}

function ipLabel(ip) {
    const local = ipLocalLabel(ip);
    if (local) return local;
    const g = pktState.geoCache.get(ip);
    if (g) return g.label || '未知';
    return pktState.geoPending ? '查询中…' : '未知';
}

async function fetchGeo() {
    const need = new Set();
    for (const r of pktState.frames) {
        for (const ip of [r.src.ip, r.dst.ip]) {
            if (!ip || ip.indexOf(':') >= 0) continue;
            if (ipLocalLabel(ip)) continue;
            if (pktState.geoCache.has(ip)) continue;
            need.add(ip);
        }
    }
    if (!need.size) return;
    pktState.geoPending = true;
    try {
        const resp = await fetch('/api/tools/packet/ip-locate', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ips: [...need] }),
        });
        if (resp.ok) {
            const data = await resp.json();
            for (const ip in data) pktState.geoCache.set(ip, data[ip]);
        } else {
            for (const ip of need) pktState.geoCache.set(ip, { label: '查询失败' });
        }
    } catch (e) {
        for (const ip of need) pktState.geoCache.set(ip, { label: '离线' });
    } finally {
        pktState.geoPending = false;
        renderView();
    }
}

// ---- 视图分发 ----
function renderView() {
    const view = pktState.view;
    if (view.startsWith('frames-')) return renderFramesTable(view);
    if (view.startsWith('sessions-')) return renderSessionsTable(view);
    if (view === 'stat-ip') return renderIpStats();
    if (view === 'stat-proto') return renderProtoStats();
    if (view === 'stat-country') return renderCountryStats();
}

function viewFramePredicate(view) {
    switch (view) {
        case 'frames-all': return () => true;
        case 'frames-arp': return r => r.l3 === 'ARP';
        case 'frames-icmp': return r => r.l4 === 'ICMP';
        case 'frames-icmpv6': return r => r.l4 === 'ICMPv6';
        case 'frames-tcp': return r => r.l4 === 'TCP';
        case 'frames-udp': return r => r.l4 === 'UDP';
    }
    return () => true;
}

function viewSessionPredicate(view) {
    switch (view) {
        case 'sessions-tcp': return s => s.l4 === 'TCP';
        case 'sessions-udp': return s => s.l4 === 'UDP';
        case 'sessions-dns': return s => s.appProto === 'DNS';
        case 'sessions-http': return s => s.appProto === 'HTTP';
        case 'sessions-tls': return s => s.appProto === 'TLS';
        case 'sessions-ssh': return s => s.appProto === 'SSH';
    }
    return () => true;
}

function filterFrames(records) {
    const f = pktState.filter;
    return records.filter(r => {
        if (f.ip) {
            const ok = (r.src.ip && r.src.ip.includes(f.ip)) || (r.dst.ip && r.dst.ip.includes(f.ip));
            if (!ok) return false;
        }
        if (f.port) {
            const ok = String(r.src.port) === f.port || String(r.dst.port) === f.port;
            if (!ok) return false;
        }
        if (f.app) {
            const u = f.app.toUpperCase();
            const hay = ((r.appProto || '') + ' ' + (r.l4 || '') + ' ' + (r.l3 || '') + ' ' + (r.tlsVersion || '')).toUpperCase();
            if (!hay.includes(u)) return false;
        }
        return true;
    });
}

function filterSessions(sessions) {
    const f = pktState.filter;
    return sessions.filter(s => {
        if (f.ip) {
            const ok = s.ip1.includes(f.ip) || s.ip2.includes(f.ip);
            if (!ok) return false;
        }
        if (f.port) {
            const ok = String(s.port1) === f.port || String(s.port2) === f.port;
            if (!ok) return false;
        }
        if (f.app) {
            const u = f.app.toUpperCase();
            const hay = ((s.appProto || '') + ' ' + (s.l4 || '') + ' ' + (s.tlsVersion || '')).toUpperCase();
            if (!hay.includes(u)) return false;
        }
        return true;
    });
}

function setViewMeta(title, count, total) {
    document.getElementById('pkt_view_title').textContent = title;
    document.getElementById('pkt_view_meta').textContent = count + (total != null && total !== count ? ` / ${total}` : '');
    document.getElementById('flt_count').textContent = `显示 ${count} / 共 ${total != null ? total : count}`;
}

// ---- 协议徽标 ----
function protoBadge(p) {
    const map = {
        'TCP': 'bg-primary', 'UDP': 'bg-success', 'ICMP': 'bg-info text-dark',
        'ICMPv6': 'bg-info text-dark', 'ARP': 'bg-warning text-dark',
        'IPv6': 'bg-secondary', 'DNS': 'bg-warning text-dark',
        'HTTP': 'bg-success', 'TLS': 'bg-info text-dark', 'SSH': 'bg-dark',
    };
    return `<span class="badge ${map[p] || 'bg-secondary'}">${p}</span>`;
}

function escapeHtml(s) {
    return (s == null ? '' : String(s)).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// ---- 表头/表体：帧列表 ----
function renderFramesTable(view) {
    const pred = viewFramePredicate(view);
    const subset = pktState.frames.filter(pred);
    const filtered = filterFrames(subset);
    const titleMap = {
        'frames-all': '全部数据包', 'frames-arp': 'ARP 数据包',
        'frames-icmp': 'ICMP 数据包', 'frames-icmpv6': 'ICMPv6 数据包',
        'frames-tcp': 'TCP 数据包', 'frames-udp': 'UDP 数据包',
    };
    setViewMeta(titleMap[view] || '数据包', filtered.length, subset.length);
    document.getElementById('pkt_thead').innerHTML = `
        <tr>
            <th style="width:50px">序号</th>
            <th style="width:130px">时间</th>
            <th>源 IP</th>
            <th>源归属地</th>
            <th style="width:60px">源端口</th>
            <th>目的 IP</th>
            <th>目的归属地</th>
            <th style="width:60px">目的端口</th>
            <th style="width:75px">协议</th>
            <th style="width:55px">长度</th>
            <th>信息</th>
        </tr>`;
    if (!filtered.length) {
        document.getElementById('pkt_tbody').innerHTML = `<tr><td colspan="11" class="text-center text-muted py-3">无匹配数据</td></tr>`;
        return;
    }
    const rows = filtered.map(r => {
        const relTs = r.relTs > 0 ? r.relTs.toFixed(6) : '0';
        return `<tr class="pkt-row" data-ridx="${r.idx}">
            <td>${r.idx + 1}</td>
            <td>${relTs}</td>
            <td>${escapeHtml(r.src.ip || r.src.mac)}</td>
            <td><small class="text-muted">${escapeHtml(ipLabel(r.src.ip))}</small></td>
            <td>${r.src.port != null ? r.src.port : ''}</td>
            <td>${escapeHtml(r.dst.ip || r.dst.mac)}</td>
            <td><small class="text-muted">${escapeHtml(ipLabel(r.dst.ip))}</small></td>
            <td>${r.dst.port != null ? r.dst.port : ''}</td>
            <td>${protoBadge(r.appProto || r.l4 || r.l3 || '?')}</td>
            <td>${r.length}</td>
            <td><small>${escapeHtml(r.info)}</small></td>
        </tr>`;
    }).join('');
    document.getElementById('pkt_tbody').innerHTML = rows;
    bindRowClick();
}

// ---- 表头/表体：会话 ----
function renderSessionsTable(view) {
    const pred = viewSessionPredicate(view);
    const subset = pktState.sessions.filter(pred);
    const filtered = filterSessions(subset);
    const titleMap = {
        'sessions-tcp': 'TCP 会话', 'sessions-udp': 'UDP 会话',
        'sessions-dns': 'DNS 会话', 'sessions-http': 'HTTP 会话',
        'sessions-tls': 'SSL/TLS 会话', 'sessions-ssh': 'SSH 会话',
    };
    setViewMeta(titleMap[view] || '通信会话', filtered.length, subset.length);
    const showDomain = view === 'sessions-dns' || view === 'sessions-http' || view === 'sessions-tls';
    document.getElementById('pkt_thead').innerHTML = `
        <tr>
            <th style="width:50px">序号</th>
            <th>IP1</th>
            <th>IP1 归属地</th>
            <th style="width:65px">IP1 端口</th>
            <th>IP2</th>
            <th>IP2 归属地</th>
            <th style="width:65px">IP2 端口</th>
            <th style="width:85px">应用协议</th>
            <th>开始时间</th>
            <th>持续时间</th>
            <th>数据包大小</th>
            <th style="width:65px">包数量</th>
            ${showDomain ? '<th>域名信息</th>' : '<th>信息</th>'}
        </tr>`;
    if (!filtered.length) {
        document.getElementById('pkt_tbody').innerHTML = `<tr><td colspan="13" class="text-center text-muted py-3">无匹配会话</td></tr>`;
        return;
    }
    const rows = filtered.map(s => {
        const appLabel = s.tlsVersion ? s.tlsVersion : s.appProto;
        const tsStr = s.tsStart > 0 ? new Date(s.tsStart * 1000).toISOString().replace('T', ' ').replace('Z', '').substring(0, 23) : '-';
        const ridx = s.firstRecIdx;
        return `<tr class="pkt-row" data-ridx="${ridx}">
            <td>${s.idx}</td>
            <td>${escapeHtml(s.ip1)}</td>
            <td><small class="text-muted">${escapeHtml(ipLabel(s.ip1))}</small></td>
            <td>${s.port1}</td>
            <td>${escapeHtml(s.ip2)}</td>
            <td><small class="text-muted">${escapeHtml(ipLabel(s.ip2))}</small></td>
            <td>${s.port2}</td>
            <td>${protoBadge(appLabel)}</td>
            <td><small>${tsStr}</small></td>
            <td>${s.duration}</td>
            <td>${formatBytes(s.bytes)}</td>
            <td>${s.frames}</td>
            <td><small>${escapeHtml(s.domain || (s.l4 + ' 会话'))}</small></td>
        </tr>`;
    }).join('');
    document.getElementById('pkt_tbody').innerHTML = rows;
    bindRowClick();
}

function formatBytes(n) {
    if (n < 1024) return n + 'B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(2) + 'KB';
    return (n / 1024 / 1024).toFixed(2) + 'MB';
}

// ---- 统计 ----
function renderIpStats() {
    const map = new Map();
    for (const r of pktState.frames) {
        for (const ip of [r.src.ip, r.dst.ip]) {
            if (!ip) continue;
            const cur = map.get(ip) || { ip: ip, count: 0, bytes: 0 };
            cur.count++; cur.bytes += r.length;
            map.set(ip, cur);
        }
    }
    const arr = [...map.values()].sort((a, b) => b.count - a.count).slice(0, 50);
    setViewMeta('IP 统计 (Top 50)', arr.length, map.size);
    document.getElementById('pkt_thead').innerHTML = `
        <tr><th style="width:60px">序号</th><th>IP</th><th>归属地</th><th>出现次数</th><th>字节数</th></tr>`;
    if (!arr.length) { document.getElementById('pkt_tbody').innerHTML = `<tr><td colspan="5" class="text-center text-muted py-3">无数据</td></tr>`; return; }
    document.getElementById('pkt_tbody').innerHTML = arr.map((x, i) => `
        <tr><td>${i + 1}</td><td>${escapeHtml(x.ip)}</td><td><small class="text-muted">${escapeHtml(ipLabel(x.ip))}</small></td><td>${x.count}</td><td>${formatBytes(x.bytes)}</td></tr>
    `).join('');
}

function renderProtoStats() {
    const map = new Map();
    for (const r of pktState.frames) {
        const key = r.appProto || r.l4 || r.l3 || '其他';
        map.set(key, (map.get(key) || 0) + 1);
    }
    const total = pktState.frames.length;
    const arr = [...map.entries()].sort((a, b) => b[1] - a[1]);
    setViewMeta('协议统计', arr.length, arr.length);
    document.getElementById('pkt_thead').innerHTML = `<tr><th>协议</th><th style="width:80px">帧数</th><th>占比</th></tr>`;
    if (!arr.length) { document.getElementById('pkt_tbody').innerHTML = `<tr><td colspan="3" class="text-center text-muted py-3">无数据</td></tr>`; return; }
    document.getElementById('pkt_tbody').innerHTML = arr.map(([k, v]) => {
        const pct = total ? (v / total * 100).toFixed(1) : 0;
        return `<tr>
            <td>${protoBadge(k)}</td>
            <td>${v}</td>
            <td><div class="progress" style="height:14px;"><div class="progress-bar" style="width:${pct}%;">${pct}%</div></div></td>
        </tr>`;
    }).join('');
}

function renderCountryStats() {
    const map = new Map();
    for (const r of pktState.frames) {
        for (const ip of [r.src.ip, r.dst.ip]) {
            if (!ip) continue;
            const lbl = ipLabel(ip) || '未知';
            // 取国家粒度（label 形如 "中国-江西省-南昌市"），第一级
            const country = lbl.split('-')[0];
            map.set(country, (map.get(country) || 0) + 1);
        }
    }
    const total = [...map.values()].reduce((a, b) => a + b, 0);
    const tail = new Set(['内网', '回环', '链路本地', '组播', '广播', '未知', '查询中…', '查询失败', '离线']);
    const arr = [...map.entries()].sort((a, b) => {
        const at = tail.has(a[0]) ? 1 : 0, bt = tail.has(b[0]) ? 1 : 0;
        if (at !== bt) return at - bt;
        return b[1] - a[1];
    });
    setViewMeta('国家统计', arr.length, arr.length);
    document.getElementById('pkt_thead').innerHTML = `<tr><th>国家/地区</th><th style="width:80px">帧数</th><th>占比</th></tr>`;
    if (!arr.length) { document.getElementById('pkt_tbody').innerHTML = `<tr><td colspan="3" class="text-center text-muted py-3">无数据</td></tr>`; return; }
    document.getElementById('pkt_tbody').innerHTML = arr.map(([k, v]) => {
        const pct = total ? (v / total * 100).toFixed(1) : 0;
        return `<tr>
            <td>${escapeHtml(k)}</td>
            <td>${v}</td>
            <td><div class="progress" style="height:14px;"><div class="progress-bar bg-success" style="width:${pct}%;">${pct}%</div></div></td>
        </tr>`;
    }).join('');
}

// ---- 行点击 / 详情 ----
function bindRowClick() {
    document.querySelectorAll('#pkt_tbody .pkt-row').forEach(tr => {
        tr.addEventListener('click', function () {
            document.querySelectorAll('#pkt_tbody .pkt-row').forEach(r => r.classList.remove('table-primary'));
            this.classList.add('table-primary');
            const ridx = parseInt(this.dataset.ridx);
            const rec = pktState.frames[ridx];
            if (rec) renderPacketDetail(rec.bytes, rec.idx, rec.ts);
        });
    });
}

// ---- 兼容：旧版函数入口（loadPacketSample 等） ----
async function parsePacketFromText() { document.getElementById('pkt_mode_paste').checked = true; pktApplyMode(); await pktDoParse(); }
async function parsePacketFromFile() { document.getElementById('pkt_mode_file').checked = true; pktApplyMode(); await pktDoParse(); }
function renderPacketList(frames, info) { loadFrames(frames, info); }
function renderPacketSingle(bytes, info) { loadFrames([{ ts: 0, bytes: bytes }], info); }

// ---- 初始化绑定 ----
(function bindPacketUI() {
    if (document.getElementById('pkt_btn_parse')) {
        document.getElementById('pkt_btn_parse').addEventListener('click', pktDoParse);
        document.getElementById('pkt_btn_reset').addEventListener('click', pktDoReset);
        document.querySelectorAll('input[name="pkt_mode"]').forEach(el => el.addEventListener('change', pktApplyMode));
        pktApplyMode();
        // 侧栏
        document.getElementById('pkt_sidebar').addEventListener('click', e => {
            const li = e.target.closest('.pkt-nav'); if (!li) return;
            if (!pktState.frames.length) return;
            document.querySelectorAll('#pkt_sidebar .pkt-nav').forEach(x => x.classList.remove('active'));
            li.classList.add('active');
            pktState.view = li.dataset.view;
            renderView();
        });
        // 筛选 (debounce 200ms)
        let fltTimer = null;
        const onFilter = () => {
            clearTimeout(fltTimer);
            fltTimer = setTimeout(() => {
                pktState.filter = {
                    ip: document.getElementById('flt_ip').value.trim(),
                    port: document.getElementById('flt_port').value.trim(),
                    app: document.getElementById('flt_app').value.trim(),
                };
                if (pktState.frames.length) renderView();
            }, 200);
        };
        ['flt_ip', 'flt_port', 'flt_app'].forEach(id => document.getElementById(id).addEventListener('input', onFilter));
        document.getElementById('flt_apply').addEventListener('click', () => { clearTimeout(fltTimer); onFilter(); });
        document.getElementById('flt_reset').addEventListener('click', () => {
            document.getElementById('flt_ip').value = '';
            document.getElementById('flt_port').value = '';
            document.getElementById('flt_app').value = '';
            pktState.filter = { ip: '', port: '', app: '' };
            if (pktState.frames.length) renderView();
        });
    }
})();

// 单帧详情（用于列表点击或单字节串）
function renderPacketDetail(bytes, idx, ts) {
    const target = document.getElementById('pkt_detail') || document.getElementById('pkt_result');
    const idxStr = (typeof idx === 'number') ? `第 ${idx + 1} 帧` : '当前包';
    const tsStr = ts ? new Date(ts * 1000).toISOString().replace('T', ' ').replace('Z', ' UTC') : '';
    const html = renderPacketSections(bytes);
    target.innerHTML = `
        <div class="card border-primary">
            <div class="card-header py-2 bg-primary text-white">
                <strong><i class="bi-search"></i> ${idxStr} 详情</strong>
                ${tsStr ? `<small class="ms-2 opacity-75">${tsStr}</small>` : ''}
                <small class="ms-2">${bytes.length} 字节</small>
            </div>
            <div class="card-body p-2">${html}</div>
        </div>
    `;
}


// 提取分层渲染逻辑（被列表详情和单帧共用）
function renderPacketSections(bytes) {
    if (bytes.length < 14) return '<div class="alert alert-warning">长度不足</div>';
    const sections = [];

    const dstMac = fmtMac(bytes, 0);
    const srcMac = fmtMac(bytes, 6);
    const etherType = (bytes[12] << 8) | bytes[13];
    const etherTypeName = ({0x0800:'IPv4', 0x0806:'ARP', 0x86dd:'IPv6', 0x8100:'802.1Q VLAN', 0x8847:'MPLS Unicast', 0x8848:'MPLS Multicast', 0x88a8:'QinQ'})[etherType] || `Unknown 0x${etherType.toString(16)}`;
    const dstOui = dstMac.replace(/:/g, '').substring(0, 6).toUpperCase();
    const srcOui = srcMac.replace(/:/g, '').substring(0, 6).toUpperCase();
    sections.push({
        title: '以太网 II (Layer 2)',
        rows: [
            ['目的 MAC', dstMac + (typeof OUI_DB !== 'undefined' && OUI_DB[dstOui] ? ` <span class="badge bg-info">${OUI_DB[dstOui]}</span>` : '')],
            ['源 MAC', srcMac + (typeof OUI_DB !== 'undefined' && OUI_DB[srcOui] ? ` <span class="badge bg-info">${OUI_DB[srcOui]}</span>` : '')],
            ['以太网类型', `0x${etherType.toString(16).padStart(4,'0')} (${etherTypeName})`],
        ],
    });

    let off = 14;

    if (etherType === 0x0800 && bytes.length >= off + 20) {
        const v_ihl = bytes[off];
        const ihl = (v_ihl & 0x0f) * 4;
        const tos = bytes[off+1];
        const totalLen = (bytes[off+2]<<8) | bytes[off+3];
        const id = (bytes[off+4]<<8) | bytes[off+5];
        const flags_frag = (bytes[off+6]<<8) | bytes[off+7];
        const flags = (flags_frag >> 13) & 0x07;
        const ttl = bytes[off+8];
        const proto = bytes[off+9];
        const checksum = (bytes[off+10]<<8) | bytes[off+11];
        const srcIp = fmtIp4(bytes, off+12);
        const dstIp = fmtIp4(bytes, off+16);
        const protoName = ({1:'ICMP',6:'TCP',17:'UDP',47:'GRE',50:'ESP',51:'AH',89:'OSPF'})[proto] || 'Unknown';
        sections.push({
            title: 'IPv4 (Layer 3)',
            rows: [
                ['版本', v_ihl >> 4],
                ['头部长度', `${ihl} 字节`],
                ['TOS/DSCP', `0x${tos.toString(16).padStart(2,'0')}`],
                ['总长度', `${totalLen} 字节`],
                ['标识 ID', `0x${id.toString(16).padStart(4,'0')} (${id})`],
                ['标志', `${flags} (DF=${(flags>>1)&1}, MF=${flags&1})`],
                ['TTL', ttl],
                ['协议', `${proto} (${protoName})`],
                ['校验和', `0x${checksum.toString(16).padStart(4,'0')}`],
                ['源 IP', srcIp],
                ['目的 IP', dstIp],
            ],
        });

        off += ihl;

        if (proto === 6 && bytes.length >= off + 20) {
            const sport = (bytes[off]<<8) | bytes[off+1];
            const dport = (bytes[off+2]<<8) | bytes[off+3];
            const seq = ((bytes[off+4]<<24) | (bytes[off+5]<<16) | (bytes[off+6]<<8) | bytes[off+7]) >>> 0;
            const ack = ((bytes[off+8]<<24) | (bytes[off+9]<<16) | (bytes[off+10]<<8) | bytes[off+11]) >>> 0;
            const dataOff = (bytes[off+12] >> 4) * 4;
            const flagsByte = bytes[off+13];
            const flagNames = [];
            if (flagsByte & 0x80) flagNames.push('CWR');
            if (flagsByte & 0x40) flagNames.push('ECE');
            if (flagsByte & 0x20) flagNames.push('URG');
            if (flagsByte & 0x10) flagNames.push('ACK');
            if (flagsByte & 0x08) flagNames.push('PSH');
            if (flagsByte & 0x04) flagNames.push('RST');
            if (flagsByte & 0x02) flagNames.push('SYN');
            if (flagsByte & 0x01) flagNames.push('FIN');
            const win = (bytes[off+14]<<8) | bytes[off+15];
            const sum = (bytes[off+16]<<8) | bytes[off+17];
            const portMap = {21:'FTP',22:'SSH',23:'Telnet',25:'SMTP',53:'DNS',80:'HTTP',110:'POP3',143:'IMAP',443:'HTTPS',445:'SMB',3306:'MySQL',3389:'RDP',5432:'PostgreSQL',8080:'HTTP-Alt'};
            const sportName = portMap[sport] ? ` (${portMap[sport]})` : '';
            const dportName = portMap[dport] ? ` (${portMap[dport]})` : '';
            sections.push({
                title: 'TCP (Layer 4)',
                rows: [
                    ['源端口', sport + sportName],
                    ['目的端口', dport + dportName],
                    ['序列号', seq],
                    ['确认号', ack],
                    ['头部长度', `${dataOff} 字节`],
                    ['标志', `0x${flagsByte.toString(16).padStart(2,'0')} [<strong>${flagNames.join(', ') || '无'}</strong>]`],
                    ['窗口大小', win],
                    ['校验和', `0x${sum.toString(16).padStart(4,'0')}`],
                ],
            });
        } else if (proto === 17 && bytes.length >= off + 8) {
            const sport = (bytes[off]<<8) | bytes[off+1];
            const dport = (bytes[off+2]<<8) | bytes[off+3];
            const len = (bytes[off+4]<<8) | bytes[off+5];
            const sum = (bytes[off+6]<<8) | bytes[off+7];
            const portMap = {53:'DNS',67:'DHCP-Server',68:'DHCP-Client',69:'TFTP',123:'NTP',161:'SNMP',162:'SNMP-Trap',500:'IKE',514:'Syslog',1812:'RADIUS'};
            const sportName = portMap[sport] ? ` (${portMap[sport]})` : '';
            const dportName = portMap[dport] ? ` (${portMap[dport]})` : '';
            sections.push({
                title: 'UDP (Layer 4)',
                rows: [
                    ['源端口', sport + sportName],
                    ['目的端口', dport + dportName],
                    ['长度', `${len} 字节`],
                    ['校验和', `0x${sum.toString(16).padStart(4,'0')}`],
                ],
            });
        } else if (proto === 1 && bytes.length >= off + 4) {
            const type = bytes[off];
            const code = bytes[off+1];
            const sum = (bytes[off+2]<<8) | bytes[off+3];
            const typeName = ({0:'Echo Reply', 8:'Echo Request', 3:'Destination Unreachable', 11:'Time Exceeded', 5:'Redirect'})[type] || 'Unknown';
            sections.push({
                title: 'ICMP (Layer 4)',
                rows: [
                    ['类型', `${type} (${typeName})`],
                    ['代码', code],
                    ['校验和', `0x${sum.toString(16).padStart(4,'0')}`],
                ],
            });
        }
    } else if (etherType === 0x0806 && bytes.length >= off + 28) {
        const op = (bytes[off+6]<<8) | bytes[off+7];
        const senderMac = fmtMac(bytes, off+8);
        const senderIp = fmtIp4(bytes, off+14);
        const targetMac = fmtMac(bytes, off+18);
        const targetIp = fmtIp4(bytes, off+24);
        const opName = op === 1 ? 'Request' : op === 2 ? 'Reply' : 'Unknown';
        sections.push({
            title: 'ARP',
            rows: [
                ['操作', `${op} (${opName})`],
                ['发送方 MAC', senderMac],
                ['发送方 IP', senderIp],
                ['目标 MAC', targetMac],
                ['目标 IP', targetIp],
            ],
        });
    }

    // HEX dump（前 256 字节）
    const dumpLines = [];
    const dumpMax = Math.min(bytes.length, 256);
    for (let i = 0; i < dumpMax; i += 16) {
        const offHex = i.toString(16).padStart(4, '0');
        const hex = [], ascii = [];
        for (let j = 0; j < 16; j++) {
            if (i + j < dumpMax) {
                const b = bytes[i + j];
                hex.push(b.toString(16).padStart(2, '0'));
                ascii.push((b >= 0x20 && b < 0x7f) ? String.fromCharCode(b) : '.');
            } else {
                hex.push('  ');
                ascii.push(' ');
            }
        }
        dumpLines.push(`<code>${offHex}</code>  ${hex.slice(0,8).join(' ')}  ${hex.slice(8).join(' ')}  <code>|${ascii.join('').replace(/</g,'&lt;')}|</code>`);
    }
    const dumpHtml = `<div class="card mt-2"><div class="card-header py-2"><strong>原始字节 (HEX 转储${bytes.length>256?'，前 256 字节':''})</strong></div>
        <div class="card-body p-2"><pre class="output-pre mb-0" style="font-size:12px;line-height:1.4;">${dumpLines.join('\n')}</pre></div></div>`;

    const html = sections.map(s => `
        <div class="card mb-2">
            <div class="card-header py-2"><strong>${s.title}</strong></div>
            <div class="card-body p-0">
                <table class="table table-sm mb-0">
                    ${s.rows.map(r => `<tr><th width="180">${r[0]}</th><td>${r[1]}</td></tr>`).join('')}
                </table>
            </div>
        </div>
    `).join('');

    return html + dumpHtml;
}

// 兼容旧调用
function parsePacket() { parsePacketFromText(); }
function renderPacket(bytes, info) { renderPacketSingle(bytes, info); }

// 初始化
// 网络计算/通用换算工具：合并后所有子模块同处一页全铺，不再切换；
// 仅 network 与 convert 页面有对应 DOM，做存在性判断后统一初始化。
// URL hash 用于兼容旧地址 302 跳转带来的锚点 —— 自动滚动到对应模块。
(function(){
    if (document.getElementById('ipCalcMask')) updateIPCalcMask();
    if (document.getElementById('mtuBase')) calcMtuAdvanced();

    function scrollToPane(key){
        var el = document.querySelector('[data-pane="' + key + '"]');
        if (el) el.scrollIntoView({behavior:'smooth', block:'start'});
    }

    // 页面载入时若 URL 带 hash（旧深链 302 跳转所得），滚动到对应模块
    var initial = location.hash.replace('#','');
    if (initial) {
        // 等 DOM 与布局稳定后再滚动，避免顶部 nav 高度未定导致定位偏移
        setTimeout(function(){ scrollToPane(initial); }, 60);
    }
    window.addEventListener('hashchange', function(){
        scrollToPane(location.hash.replace('#',''));
    });
})();
