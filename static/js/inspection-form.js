let _deviceList = [];
let _addedIds = new Set();

// 加载巡检模板（用于检查项自动匹配）
window._templates = [];
(function() {
    fetch('/api/inspection-templates')
        .then(function(r) { return r.json(); })
        .then(function(t) { window._templates = t; })
        .catch(function() {});
})();

document.addEventListener('DOMContentLoaded', function() {
    var sel = document.getElementById('customerSelect');
    if (sel) sel.addEventListener('change', function() { onCustomerChange(this); });
    // 如果客户已预选，自动加载设备
    if (sel && sel.value) {
        setTimeout(function() { onCustomerChange(sel); }, 300);
    }
});
function onCustomerChange(sel) {
    const cid = sel.value;
    const address = sel.options[sel.selectedIndex]?.dataset?.address || '';
    document.getElementById('locationInput').value = address;

    _addedIds.clear();
    const selEl = document.getElementById('deviceSelector');
    selEl.innerHTML = '<option value="">-- 从设备库中选择 --</option>';
    selEl.disabled = true;
    document.getElementById('devicesContainer').innerHTML =
        '<div class="text-muted text-center py-3" id="noDeviceHint">选择客户后自动加载设备</div>';

    if (!cid) return;

    fetch('/api/customers/' + cid + '/devices')
        .then(r => { if (!r.ok) throw new Error('API error ' + r.status); return r.json(); })
        .then(devices => {
            _deviceList = devices;
            // 先创建设备卡片
            for (var di = 0; di < devices.length; di++) {
                var d = devices[di];
                try { addDeviceCard(d); } catch(e) { showToast('设备卡片加载失败: ' + (e.message || e), 'danger'); }
                _addedIds.add(d.id);
            }
            // 填充下拉选项
            selEl.disabled = devices.length === 0;
            selEl.options.length = 1; // 保留第一个空选项
            for (var di = 0; di < devices.length; di++) {
                var d = devices[di];
                var opt = document.createElement('option');
                opt.value = d.id;
                opt.text = d.device_name + (d.ip_address ? ' (' + d.ip_address + ')' : '');
                opt.setAttribute('data-name', d.device_name);
                opt.setAttribute('data-ip', d.ip_address || '');
                opt.setAttribute('data-type', d.device_type || '');
                opt.setAttribute('data-model', d.model || '');
                opt.setAttribute('data-osversion', d.os_version || '');
                opt.setAttribute('data-cname', d.customer_name || '');
                opt.setAttribute('data-caddr', d.customer_address || '');
                opt.setAttribute('data-location', d.location || '');
                selEl.appendChild(opt);
            }
            if (devices.length === 0) {
                document.getElementById('devicesContainer').innerHTML =
                    '<div class="text-muted text-center py-3">该客户暂无设备</div>';
            }
        }).catch(function(err) {
            showToast('加载设备失败：' + err.message, 'danger');
        });
}

function addSelectedDevice(sel) {
    const val = sel.value;
    if (!val) return;
    const opt = sel.options[sel.selectedIndex];
    const deviceId = parseInt(val);
    if (_addedIds.has(deviceId)) {
        showToast('该设备已在巡检清单中', 'warning');
        sel.value = '';
        return;
    }
    function ga(name) { return opt.getAttribute(name) || ''; }
    addDeviceCard({
        device_name: ga('data-name'),
        ip_address: ga('data-ip'),
        device_type: ga('data-type'),
        model: ga('data-model'),
        os_version: ga('data-osversion'),
        location: ga('data-location'),
        customer_name: ga('data-cname'),
        customer_address: ga('data-caddr'),
    });
    _addedIds.add(deviceId);
    sel.value = '';
}

function addAllDevices() {
    const sel = document.getElementById('deviceSelector');
    const options = sel.querySelectorAll('option');
    let count = 0;
    for (var oi = 0; oi < options.length; oi++) {
        var opt = options[oi];
        if (!opt.value) continue;
        var deviceId = parseInt(opt.value);
        if (_addedIds.has(deviceId)) continue;
        function ga(name) { return opt.getAttribute(name) || ''; }
        addDeviceCard({
            device_name: ga('data-name'),
            ip_address: ga('data-ip'),
            device_type: ga('data-type'),
            model: ga('data-model'),
            os_version: ga('data-osversion'),
            location: ga('data-location'),
            customer_name: ga('data-cname'),
            customer_address: ga('data-caddr'),
        });
        _addedIds.add(deviceId);
        count++;
    }
    if (count === 0) showToast('所有设备已添加', 'info');
}

function addDeviceCard(deviceData) {
    // deviceData: {device_name, ip_address, device_type, model, os_version, customer_name, customer_address}
    document.getElementById('noDeviceHint')?.remove();
    const tmpl = document.getElementById('deviceTemplate');
    const clone = tmpl.content.cloneNode(true);

    const name = deviceData.device_name || '';
    const dtype = deviceData.device_type || '';

    clone.querySelector('.device-name-display').textContent = name;
    clone.querySelector('.device-type-badge').textContent = dtype || '未分类';
    clone.querySelector('.device-location').textContent = deviceData.location || '-';
    clone.querySelector('.device-model-display').textContent = deviceData.model || '-';
    clone.querySelector('.device-ip-display').textContent = deviceData.ip_address || '-';
    clone.querySelector('.device-osversion').textContent = deviceData.os_version || '-';

    // 按设备类型匹配模板检查项
    const itemsContainer = clone.querySelector('.check-items');
    var matchedItems = null;
    if (dtype && window._templates) {
        var t = window._templates.find(function(t) { return t.device_type === dtype && t.items && t.items.length > 0; });
        if (t) matchedItems = t.items;
    }
    if (!matchedItems) {
        matchedItems = [{name:'运行状态',default_result:'正常'},{name:'CPU使用率',default_result:'正常'},{name:'内存使用率',default_result:'正常'},{name:'端口状态',default_result:'正常'},{name:'告警检查',default_result:'正常'}];
    }
    matchedItems.forEach(function(item) {
        var itm = document.getElementById('checkItemTemplate').content.cloneNode(true);
        itm.querySelector('.check-name').value = item.name || '';
        itm.querySelector('.check-result').value = item.default_result || '正常';
        itemsContainer.appendChild(itm);
    });

    document.getElementById('devicesContainer').appendChild(clone);
}

function addCheckItem(btn) {
    const container = btn.closest('.device-item').querySelector('.check-items');
    const tmpl = document.getElementById('checkItemTemplate');
    container.appendChild(tmpl.content.cloneNode(true));
}

// 设置报告日期
function setReportDate() {
    var d = new Date();
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    document.getElementById('reportDateDisplay').textContent = y + '年' + m + '月' + day + '日';
}

// 拓扑图上传
function addTopologyPhoto(btn) {
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = function() {
        var file = input.files[0];
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) { showToast('图片不能超过10MB', 'warning'); return; }
        var formData = new FormData();
        formData.append('photo', file);
        var btnParent = btn.closest('.mb-3');
        var list = btnParent.querySelector('.topology-photo-list');
        var placeholder = document.createElement('div');
        placeholder.innerHTML = '<i class="bi-arrow-clockwise"></i> 上传中...';
        list.appendChild(placeholder);
        fetch('/api/upload-photo', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (data.error) { placeholder.innerHTML = '<span class="text-danger">失败</span>'; return; }
                placeholder.outerHTML = '<div class="photo-item" style="position:relative;display:inline-block;">' +
                    '<img src="/' + data.path + '" style="width:150px;height:100px;object-fit:cover;border-radius:4px;border:1px solid #ddd;">' +
                    '<button type="button" class="btn btn-sm btn-danger" style="position:absolute;top:-6px;right:-6px;padding:0 6px;font-size:var(--fs-sm);line-height:18px;border-radius:50%;" onclick="this.parentElement.remove()">×</button>' +
                    '<input type="hidden" class="topology-photo-path" value="' + data.path + '">' +
                    '</div>';
            })
            .catch(function() { placeholder.innerHTML = '<span class="text-danger">上传失败</span>'; });
    };
    input.click();
}

// 章节照片上传（通用）
function addSectionPhoto(btn, section) {
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = function() {
        var file = input.files[0];
        if (!file || file.size > 10 * 1024 * 1024) { showToast('图片不能超过10MB', 'warning'); return; }
        var formData = new FormData();
        formData.append('photo', file);
        var list = btn.closest('.mb-2').querySelector('.' + section + '-photo-list');
        var ph = document.createElement('div');
        ph.innerHTML = '<i class="bi-arrow-clockwise"></i>';
        list.appendChild(ph);
        fetch('/api/upload-photo', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (data.error) { ph.innerHTML = '失败'; return; }
                ph.outerHTML = '<div class="photo-item" style="position:relative;display:inline-block;">' +
                    '<img src="/' + data.path + '" style="width:120px;height:90px;object-fit:cover;border-radius:4px;border:1px solid #ddd;">' +
                    '<button type="button" class="btn btn-sm btn-danger" style="position:absolute;top:-6px;right:-6px;padding:0 6px;font-size:var(--fs-sm);line-height:18px;border-radius:50%;" onclick="this.parentElement.remove()">×</button>' +
                    '<input type="hidden" class="section-photo" data-section="' + section + '" value="' + data.path + '">' +
                    '</div>';
            });
    };
    input.click();
}

// 上传印章图片
function addSealImage(btn) {
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/png,image/jpeg';
    input.onchange = function() {
        var file = input.files[0];
        if (!file) return;
        if (file.size > 5 * 1024 * 1024) { showToast('图片不能超过5MB', 'warning'); return; }
        var formData = new FormData();
        formData.append('photo', file);
        var container = btn.closest('.mb-3').querySelector('.seal-preview');
        container.innerHTML = '<i class="bi-arrow-clockwise"></i> 上传中...';
        fetch('/api/upload-photo', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (data.error) { container.innerHTML = '<span class="text-danger">失败</span>'; return; }
                container.innerHTML = '<div class="photo-item" style="position:relative;display:inline-block;">' +
                    '<img src="/' + data.path + '" style="height:60px;border-radius:4px;border:1px solid #ddd;">' +
                    '<button type="button" class="btn btn-sm btn-danger" style="position:absolute;top:-8px;right:-8px;padding:0 6px;font-size:var(--fs-sm);line-height:18px;border-radius:50%;" onclick="this.parentElement.remove()">×</button>' +
                    '<input type="hidden" class="seal-image-path" value="' + data.path + '">' +
                    '</div>';
            })
            .catch(function() { container.innerHTML = '<span class="text-danger">上传失败</span>'; });
    };
    input.click();
}

// 添加现场照片（上传到服务器，存路径）
function addPhoto(btn) {
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.multiple = true;
    input.onchange = function() {
        var photoList = btn.closest('.device-item').querySelector('.photo-list');
        for (var i = 0; i < input.files.length; i++) {
            var file = input.files[i];
            if (file.size > 10 * 1024 * 1024) { showToast('图片不能超过10MB', 'warning'); continue; }
            // 逐个上传到服务器
            var formData = new FormData();
            formData.append('photo', file);
            var placeholder = document.createElement('div');
            placeholder.className = 'photo-item';
            placeholder.style.cssText = 'display:inline-block;text-align:center;padding:10px;';
            placeholder.innerHTML = '<i class="bi-arrow-clockwise"></i> 上传中...';
            photoList.appendChild(placeholder);
            fetch('/api/upload-photo', { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => {
                    if (data.error) { placeholder.innerHTML = '<span class="text-danger">上传失败</span>'; return; }
                    placeholder.innerHTML = '<div style="position:relative;display:inline-block;">' +
                        '<img src="' + data.url + '" style="width:120px;height:90px;object-fit:cover;border-radius:4px;border:1px solid #ddd;">' +
                        '<button type="button" class="btn btn-sm btn-danger" style="position:absolute;top:-6px;right:-6px;padding:0 6px;font-size:var(--fs-sm);line-height:18px;border-radius:50%;" onclick="this.parentElement.parentElement.remove()">×</button>' +
                        '<input type="hidden" class="photo-path" value="' + data.path + '">' +
                        '</div>';
                })
                .catch(function() { placeholder.innerHTML = '<span class="text-danger">上传失败</span>'; });
        }
    };
    input.click();
}

function removeDevice(btn) {
    const card = btn.closest('.device-item');
    const name = card.querySelector('.device-name-display')?.textContent || '';
    const matching = _deviceList.find(function(d) { return d.device_name === name; });
    if (matching) _addedIds.delete(matching.id);
    card.remove();
    if (document.querySelectorAll('.device-item').length === 0) {
        document.getElementById('devicesContainer').innerHTML =
            '<div class="text-muted text-center py-3" id="noDeviceHint">选择客户后自动加载设备</div>';
    }
}

function saveInspection() {
    const devices = [];
    document.querySelectorAll('.device-item').forEach(el => {
        const device = {
            device: el.querySelector('.device-name-display')?.textContent || '',
            ip: el.querySelector('.device-ip-display')?.textContent || '',
            type: el.querySelector('.device-type-badge')?.textContent || '',
            model: el.querySelector('.device-model-display')?.textContent || '',
            os_version: el.querySelector('.device-osversion')?.textContent || '',
            location: el.querySelector('.device-location')?.textContent || '',
            uptime: el.querySelector('.device-uptime')?.value || '',
            items: [],
            photos: []
        };
        el.querySelectorAll('.check-item').forEach(ci => {
            device.items.push({
                name: ci.querySelector('.check-name').value,
                result: ci.querySelector('.check-result').value,
                remark: ci.querySelector('.check-remark').value
            });
        });
        el.querySelectorAll('.photo-path').forEach(p => {
            device.photos.push(p.value);
        });
        devices.push(device);
    });
    if (devices.length === 0) {
        showToast('请至少添加一个巡检设备', 'warning');
        return false;
    }
    document.getElementById('contentJson').value = JSON.stringify(devices);
    // 保存章节内容
    var topoPhotos = [];
    document.querySelectorAll('.topology-photo-path').forEach(function(el) { topoPhotos.push(el.value); });
    var sealEl = document.querySelector('.seal-image-path');
    // 收集章节照片（按 section 分组）
    var q2_3_photos = []; var q2_4_photos = [];
    document.querySelectorAll('.section-photo').forEach(function(el) {
        if (el.dataset.section === 'q2_3') q2_3_photos.push(el.value);
        if (el.dataset.section === 'q2_4') q2_4_photos.push(el.value);
    });
    var sections = {
        network_topology: document.querySelector('[name="s_network_topology"]')?.value || '',
        topology_photos: topoPhotos,
        q2_1: document.querySelector('[name="s_q2_1"]')?.value || '',
        q2_2: document.querySelector('[name="s_q2_2"]')?.value || '',
        q2_3: document.querySelector('[name="s_q2_3"]')?.value || '',
        q2_4: document.querySelector('[name="s_q2_4"]')?.value || '',
        q2_3_photos: q2_3_photos,
        q2_4_photos: q2_4_photos,
        device_ledger: document.querySelector('[name="s_device_ledger"]')?.value || '',
        flood_advice: document.querySelector('[name="s_flood_advice"]')?.value || '',
        tech_support: document.querySelector('[name="s_tech_support"]')?.value || '',
        complaint: document.querySelector('[name="s_complaint"]')?.value || '',
        owner_sign: document.querySelector('[name="s_owner_sign"]')?.value || '',
        seal_image: sealEl ? sealEl.value : '',
    };
    document.getElementById('sectionsJson').value = JSON.stringify(sections);
    for (const d of devices) {
        if (!d.device) { showToast('请填写设备名称', 'warning'); return false; }
    }
    return true;
}

document.addEventListener('DOMContentLoaded', function() {
    setReportDate();
if (window._inspectionData) {
    const data = JSON.parse(window._inspectionData);
    if (data && data.length > 0) {
        setTimeout(() => {
            data.forEach(d => {
                addDeviceCard({
                    device_name: d.device,
                    ip_address: d.ip,
                    device_type: d.type,
                    model: d.model || '',
                    os_version: d.os_version || '',
                    location: d.location || '',
                    customer_name: '',
                    customer_address: ''
                });
                const container = document.getElementById('devicesContainer');
                const last = container.lastElementChild;
                if (last) {
                    // 设置运行时间
                    const uptime = last.querySelector('.device-uptime');
                    if (uptime && d.uptime) uptime.value = d.uptime;
                    // 加载检查项
                    const ciContainer = last.querySelector('.check-items');
                    ciContainer.innerHTML = '';
                    (d.items || []).forEach(item => {
                        const tmpl = document.getElementById('checkItemTemplate').content.cloneNode(true);
                        tmpl.querySelector('.check-name').value = item.name || '';
                        tmpl.querySelector('.check-result').value = item.result || '正常';
                        tmpl.querySelector('.check-remark').value = item.remark || '';
                        ciContainer.appendChild(tmpl);
                    });
                    // 加载照片
                    if (d.photos && d.photos.length > 0) {
                        var photoList = last.querySelector('.photo-list');
                        photoList.innerHTML = '';
                        d.photos.forEach(function(path) {
                            var div = document.createElement('div');
                            div.className = 'photo-item';
                            div.style.cssText = 'position:relative;display:inline-block;';
                            div.innerHTML = '<img src="/' + path + '" style="width:120px;height:90px;object-fit:cover;border-radius:4px;border:1px solid #ddd;">' +
                                '<button type="button" class="btn btn-sm btn-danger" style="position:absolute;top:-6px;right:-6px;padding:0 6px;font-size:var(--fs-sm);line-height:18px;border-radius:50%;" onclick="this.parentElement.remove()">×</button>' +
                                '<input type="hidden" class="photo-path" value="' + path + '">';
                            photoList.appendChild(div);
                        });
                    }
                }
            });
        }, 500);
    }
}
});

// ============================================================
// V4: 设备自动匹配 + 复合巡检表单
// ============================================================
var customerSelect = document.getElementById('customerSelect');
var currentCustomerId = window._currentCustomerId || 0;

if (customerSelect) {
    customerSelect.addEventListener('change', function() {
        currentCustomerId = this.value;
        if (currentCustomerId) { loadCustomerDevices(); }
    });
    // 编辑模式：自动加载
    if (currentCustomerId) { loadCustomerDevices(); }
}

function loadCustomerDevices() {
    var container = document.getElementById('devicesContainer');
    var hint = document.getElementById('noDeviceHint');
    var loading = document.getElementById('devicesLoading');
    if (!currentCustomerId) {
        container.innerHTML = '';
        container.appendChild(hint);
        hint.classList.remove('d-none');
        return;
    }
    hint.classList.add('d-none');
    if (loading) loading.classList.remove('d-none');

    fetch('/api/customers/' + currentCustomerId + '/devices-with-templates')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            container.innerHTML = '';
            if (!data.devices || data.devices.length === 0) {
                container.innerHTML = '<div class="text-muted text-center py-3">该客户暂无可巡检设备</div>';
                return;
            }
            // 按类别分组
            var grouped = {};
            data.devices.forEach(function(d) {
                var cat = d.matched_template_category || '其他';
                if (!grouped[cat]) grouped[cat] = [];
                grouped[cat].push(d);
            });
            var catOrder = ['服务器','网络设备','安全设备','UPS','空调','其他'];
            catOrder.forEach(function(cat) {
                if (grouped[cat]) {
                    container.innerHTML += '<h6 class="mt-3 mb-2 text-muted"><i class="bi-folder2 me-2"></i>' + cat + ' (' + grouped[cat].length + '台)</h6>';
                    grouped[cat].forEach(function(d) { renderDeviceCard(d, container); });
                }
            });
        })
        .catch(function() { container.innerHTML = '<div class="text-danger text-center py-3">加载失败，请刷新重试</div>'; });
}

function renderDeviceCard(d, container) {
    var card = document.createElement('div');
    card.className = 'device-item card mb-2 border-primary';
    card.id = 'deviceCard_' + d.device_id;
    card.dataset.deviceId = d.device_id;
    card.dataset.templateId = d.matched_template_id || '';

    var matchBadge = d.match_type === 'model' ? '🎯 型号匹配' : d.match_type === 'device_type' ? '🔧 类型匹配' : '⚠️ 未匹配';
    var matchColor = d.match_type === 'none' ? 'text-danger' : 'text-success';

    card.innerHTML =
        '<div class="card-header py-1 d-flex justify-content-between align-items-center surface-muted">' +
            '<strong>' + d.device_name + '</strong>' +
            '<div><span class="badge bg-' + (d.match_type !== 'none' ? 'info' : 'warning') + ' me-1">' + d.matched_template_name + '</span>' +
            '<small class="' + matchColor + '">' + matchBadge + '</small></div>' +
        '</div>' +
        '<div class="card-body py-2">' +
            '<div class="row g-1 mb-2 small text-muted">' +
                '<div class="col-md-3">📍 ' + (d.location || '-') + '</div>' +
                '<div class="col-md-3">🔧 ' + (d.model || '-') + '</div>' +
                '<div class="col-md-3">🌐 ' + (d.ip_address || '-') + '</div>' +
                '<div class="col-md-3">💻 ' + (d.os_version || '-') + '</div>' +
            '</div>' +
            '<div class="row g-1 small text-muted mb-2">' +
                '<div class="col-md-6">⏱ 系统运行时间：<input type="text" class="form-control form-control-sm d-inline-block" style="width:140px" placeholder="如：30天 2小时" data-device="' + d.device_id + '" data-field="系统运行时间"></div>' +
            '</div>' +
            '<hr class="my-1"><div class="check-items" id="checkItems_' + d.device_id + '">' +
            '<div class="text-center text-muted py-2 small">请先为设备关联巡检模板</div></div>' +
        '</div>';
    container.appendChild(card);

    // 加载模板检查项
    if (d.matched_template_id) {
        fetch('/api/inspection-templates')
            .then(function(r) { return r.json(); })
            .then(function(templates) {
                var t = templates.find(function(x) { return x.id === d.matched_template_id; });
                if (t && t.items) {
                    var itemsDiv = document.getElementById('checkItems_' + d.device_id);
                    itemsDiv.innerHTML = '';
                    t.items.forEach(function(item, idx) {
                        if (item.enabled === false) return;
                        itemsDiv.appendChild(renderCheckItem(item, d.device_id, idx));
                    });
                }
            });
    }
}

function renderCheckItem(item, deviceId, idx) {
    // V14: 支持 sub_items 自定义组合 — 一个主项目可有多个子输入（如「状态 + 照片」）
    var subs = (item.sub_items && item.sub_items.length) ? item.sub_items : null;
    if (subs) {
        // 多子项目：返回包裹了所有子项目行的容器
        var wrapper = document.createElement('div');
        wrapper.className = 'mb-2 check-item-group border-start border-3 ps-2';
        wrapper.dataset.deviceId = deviceId;
        var header = document.createElement('div');
        header.className = 'small text-muted mb-1';
        header.innerHTML = '<i class="bi-list-nested me-1"></i><strong>' + escHtml(item.name) +
            (item.help_text ? ' <i class="bi-info-circle text-info" title="'+escAttr(item.help_text)+'"></i>' : '') + '</strong>';
        wrapper.appendChild(header);
        subs.forEach(function(sub){
            var fieldKey = item.name + (sub.label ? '.' + sub.label : '');
            wrapper.appendChild(renderSubItemRow(sub, item, deviceId, fieldKey));
        });
        return wrapper;
    }
    // 旧格式（单 field_type）：保留单行显示
    return renderSubItemRow(item, item, deviceId, item.name, /*isFlat*/true);
}

function escHtml(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escAttr(s){ return escHtml(s).replace(/"/g,'&quot;'); }

// 单个子项目（或旧格式单字段）的输入行
function renderSubItemRow(sub, parentItem, deviceId, fieldKey, isFlat) {
    var div = document.createElement('div');
    div.className = 'row mb-1 align-items-center check-item';
    div.dataset.field = fieldKey;
    div.dataset.deviceId = deviceId;
    div.dataset.fieldType = sub.field_type || 'text';

    var labelText = isFlat ? parentItem.name : (sub.label || '子项');
    var helpText = sub.help_text || parentItem.help_text || '';
    var labelHtml = '<label class="col-form-label col-form-label-sm col-md-3 text-end" title="' + escAttr(helpText) + '">' +
        escHtml(labelText) + (sub.required ? '<span class="text-danger">*</span>' : '') +
        (helpText ? ' <i class="bi-info-circle text-info ms-1" title="' + escAttr(helpText) + '"></i>' : '') +
        '</label>';

    var inputHtml = '';
    var ft = sub.field_type || 'text';
    var fkAttr = ' data-device="' + deviceId + '" data-field="' + escAttr(fieldKey) + '"';
    switch (ft) {
        case 'dropdown':
        case 'status_note':
        case 'status_abnormal':
            var defaultOpts = (ft === 'status_abnormal') ? '正常,异常' : '正常,不正常';
            var opts = (sub.options || defaultOpts).split(',');
            inputHtml = '<select class="form-select form-select-sm check-value"' + fkAttr + '>';
            opts.forEach(function(o) { inputHtml += '<option>' + escHtml(o.trim()) + '</option>'; });
            inputHtml += '</select>';
            if (sub.required && sub.allow_skip) {
                inputHtml += '<div class="skip-area mt-1 d-none">' +
                    '<select class="form-select form-select-sm skip-reason" style="width:auto"><option value="">--跳过原因--</option>' +
                    (sub.skip_reasons || '').split(',').filter(Boolean).map(function(r){return '<option>'+escHtml(r.trim())+'</option>';}).join('') +
                    '<option value="其他">其他</option></select>' +
                    '<textarea class="form-control form-control-sm mt-1 skip-detail" rows="1" placeholder="详细说明"></textarea></div>';
            }
            break;
        case 'percentage':
            inputHtml = '<div class="input-group input-group-sm">' +
                '<select class="form-select check-value"' + fkAttr + ' style="max-width:100px;"><option>正常</option><option>不正常</option></select>' +
                '<input type="number" class="form-control check-value" data-device="' + deviceId + '" data-field="' + escAttr(fieldKey) + '.百分比" min="0" max="100" placeholder="百分比">' +
                '<span class="input-group-text">%</span></div>';
            break;
        case 'ping_test':
            inputHtml = '<div class="input-group input-group-sm">' +
                '<input type="text" class="form-control check-value" data-device="' + deviceId + '" data-field="' + escAttr(fieldKey) + '.目标" value="' + escAttr(sub.ping_target_default || '') + '" placeholder="Ping 目标">' +
                '<select class="form-select check-value"' + fkAttr + ' style="max-width:120px;"><option>通</option><option>不通</option><option>丢包</option></select></div>';
            break;
        case 'text':
            inputHtml = '<input type="text" class="form-control form-control-sm check-value"' + fkAttr + ' placeholder="' + escAttr(sub.placeholder || '') + '">';
            break;
        case 'multiline_text':
            inputHtml = '<textarea class="form-control form-control-sm check-value" rows="2"' + fkAttr + ' placeholder="' + escAttr(sub.placeholder || '') + '"></textarea>';
            break;
        case 'number':
            inputHtml = '<input type="number" class="form-control form-control-sm check-value"' + fkAttr + ' step="0.1">';
            break;
        case 'date':
            inputHtml = '<input type="date" class="form-control form-control-sm check-value"' + fkAttr + '>';
            break;
        case 'image':
            inputHtml = '<input type="file" class="form-control form-control-sm check-photo" accept="image/*"' + fkAttr + ' onchange="uploadCheckPhoto(this)">';
            break;
        case 'version_check':
            inputHtml = '<div class="input-group input-group-sm">' +
                '<span class="input-group-text">系统</span>' +
                '<input type="text" class="form-control check-value" data-device="' + deviceId + '" data-field="' + escAttr(fieldKey) + '.系统版本" placeholder="如 V7.0.2">' +
                '<span class="input-group-text">规则库</span>' +
                '<input type="text" class="form-control check-value" data-device="' + deviceId + '" data-field="' + escAttr(fieldKey) + '.规则库版本" placeholder="如 IPS-20260101"></div>';
            break;
        case 'config_backup':
            inputHtml = '<div class="row g-1">' +
                '<div class="col-md-7"><input type="file" class="form-control form-control-sm check-config-file" accept=".txt,.cfg,.conf,.log,.cli,.bak"' +
                    ' data-device="' + deviceId + '" data-field="' + escAttr(fieldKey) + '" onchange="uploadCheckConfig(this)"></div>' +
                '<div class="col-md-5"><input type="text" class="form-control form-control-sm check-value" data-device="' + deviceId + '" data-field="' + escAttr(fieldKey) + '.版本号" placeholder="版本号 / 备注"></div>' +
                '</div>';
            break;
        default:
            inputHtml = '<input type="text" class="form-control form-control-sm check-value"' + fkAttr + '>';
    }

    div.innerHTML = labelHtml + '<div class="col-md-8">' + inputHtml + '</div>';

    // Dropdown/status change: show skip reason if "非正常" value selected
    if ((ft === 'dropdown' || ft === 'status_note' || ft === 'status_abnormal') && sub.required && sub.allow_skip) {
        setTimeout(function() {
            var sel = div.querySelector('.check-value');
            if (sel) {
                sel.addEventListener('change', function() {
                    var skipArea = this.parentElement.querySelector('.skip-area');
                    if (skipArea) {
                        var normalVals = ['正常', '符合要求'];
                        skipArea.classList.toggle('d-none', normalVals.includes(this.value));
                    }
                });
            }
        }, 0);
    }

    return div;
}

// 巡检表单中 config_backup 字段：选择文件后立即上传到设备的配置备份历史
function uploadCheckConfig(input) {
    var file = input.files[0];
    if (!file) return;
    var deviceId = input.dataset.device;
    var formData = new FormData();
    formData.append('file', file);
    // 尝试拿同行的版本号
    var versionInput = input.closest('.row').querySelector('input[data-field$=".版本号"]');
    if (versionInput && versionInput.value) {
        formData.append('version', versionInput.value);
    }
    fetch('/api/devices/' + deviceId + '/config-backups/upload-from-inspection', {method:'POST', body:formData})
        .then(function(r){return r.json();})
        .then(function(data){
            if (data.success) {
                // 把备份 id / 文件名写入 input 的 data 属性，并显示提示
                input.dataset.backupId = data.backup_id;
                input.dataset.filePath = data.file_path;
                var hint = document.createElement('small');
                hint.className = 'text-success ms-2 d-block';
                hint.innerHTML = '<i class="bi-check-circle"></i> 已上传：' + data.filename + ' (#' + data.backup_id + ')';
                // 移除前一次提示
                var prev = input.parentElement.querySelector('small.text-success');
                if (prev) prev.remove();
                input.parentElement.appendChild(hint);
            } else {
                showToast('上传失败：' + (data.error || '未知错误'), 'danger');
            }
        })
        .catch(function(e){ showToast('上传失败：' + e, 'danger'); });
}

function uploadCheckPhoto(input) {
    var file = input.files[0];
    if (!file) return;
    var formData = new FormData();
    formData.append('file', file);
    fetch('/api/upload-photo', {method:'POST', body:formData})
        .then(function(r){return r.json();})
        .then(function(data){
            if (data.path) {
                // Show preview
                var preview = document.createElement('img');
                preview.src = '/' + data.path;
                preview.style.cssText = 'width:80px;height:60px;object-fit:cover;margin-top:4px;border-radius:4px;';
                preview.dataset.photoPath = data.path;
                input.parentElement.appendChild(preview);
                input.type = 'hidden';
                input.value = data.path;
            }
        });
}

// 收集所有设备的检查项值为 JSON
function saveInspection() {
    var fieldValues = {};
    var skipReasons = {};
    var deviceIds = [];

    document.querySelectorAll('.device-item').forEach(function(card) {
        var did = card.dataset.deviceId;
        if (!did) return;
        deviceIds.push(parseInt(did));
        var devName = card.querySelector('strong');
        var devKey = devName ? devName.textContent : ('设备' + did);

        fieldValues[devKey] = {};
        skipReasons[devKey] = {};

        card.querySelectorAll('.check-value').forEach(function(el) {
            var fname = el.dataset.field;
            if (!fname) return;
            fieldValues[devKey][fname] = el.value;
            // Check for skip reason
            var skipArea = el.parentElement.querySelector('.skip-area');
            if (skipArea && !skipArea.classList.contains('d-none')) {
                var reason = skipArea.querySelector('.skip-reason');
                var detail = skipArea.querySelector('.skip-detail');
                if (reason && reason.value) {
                    skipReasons[devKey][fname] = {reason: reason.value, detail: detail ? detail.value : ''};
                }
            }
        });

        // Also collect uptime
        var uptimeInput = card.querySelector('[data-field="系统运行时间"]');
        if (uptimeInput && uptimeInput.value) {
            fieldValues[devKey]['系统运行时间'] = uptimeInput.value;
        }
    });

    document.getElementById('fieldValuesJson').value = JSON.stringify(fieldValues);
    document.getElementById('skipReasonsJson').value = JSON.stringify(skipReasons);
    document.getElementById('deviceIdsJson').value = JSON.stringify(deviceIds);
    // 提交成功后清掉草稿（在表单 action 真正提交后由路由 redirect，无法 hook 成功事件——所以在 unload 前不删，提交后由用户手动删/或下次进入时检测到记录已生成自动清理）
    if (window._draftDeleteOnSubmit) {
        try { window._draftDeleteOnSubmit(); } catch(e) {}
    }
    return true;
}

// ============================ V11: 草稿自动保存 ============================
(function setupDraftAutoSave(){
    // 仅在新建/编辑模式启用
    var taskIdEl = document.querySelector('[name="task_id"]');
    var inspectionIdEl = document.querySelector('[name="inspection_id"]');  // 编辑模式（如果有）
    var formTypeBase = 'inspection';
    var relatedId = null;
    if (inspectionIdEl && inspectionIdEl.value) {
        // 编辑模式：以巡检记录 id 关联
        relatedId = parseInt(inspectionIdEl.value);
        formTypeBase = 'inspection_edit';
    } else if (taskIdEl && taskIdEl.value) {
        // 新建模式：以任务 id 关联
        relatedId = parseInt(taskIdEl.value);
    } else {
        // 无 task_id 也无 inspection_id：用 0 做匿名草稿
        relatedId = 0;
    }
    var formType = formTypeBase;
    var saveTimer = null;
    var lastSavedHash = '';
    var indicator = null;

    function getIndicator(){
        if (indicator) return indicator;
        var bar = document.createElement('div');
        bar.id = 'draftIndicator';
        bar.className = 'draft-indicator';
        bar.innerHTML = '<i class="bi-cloud-check me-1 text-success"></i><span class="draft-text">草稿已保存</span>';
        document.body.appendChild(bar);
        indicator = bar;
        return indicator;
    }

    function setIndicator(text, type){
        var bar = getIndicator();
        bar.style.display = '';
        var icon = type==='saving' ? '<i class="bi-arrow-repeat me-1 text-primary"></i>'
                : type==='error'  ? '<i class="bi-exclamation-triangle me-1 text-danger"></i>'
                : '<i class="bi-cloud-check me-1 text-success"></i>';
        bar.innerHTML = icon + '<span class="draft-text">'+text+'</span>';
        clearTimeout(bar._hideT);
        if (type !== 'saving') bar._hideT = setTimeout(function(){ bar.style.display='none'; }, 3500);
    }

    function snapshot(){
        // 收集表单核心字段（不含文件）
        var form = document.querySelector('form');
        if (!form) return null;
        var data = {};
        // 1. 原生字段
        Array.from(form.elements).forEach(function(el){
            if (!el.name) return;
            if (el.type === 'file') return;
            if (el.type === 'checkbox' || el.type === 'radio') {
                if (el.checked) {
                    if (data[el.name]) data[el.name] = [].concat(data[el.name], [el.value]);
                    else data[el.name] = el.value;
                }
            } else {
                data[el.name] = el.value;
            }
        });
        // 2. 设备区块的所有 input/select/textarea（包括动态生成的）
        var devData = [];
        document.querySelectorAll('.device-item').forEach(function(card){
            var dev = {meta:{}, items:[]};
            // 设备元数据
            card.querySelectorAll('input[data-field], select[data-field], textarea[data-field]').forEach(function(el){
                dev.meta[el.dataset.field] = el.value;
            });
            // 检查项 — 兼容多种结构
            card.querySelectorAll('.check-item, .check-row').forEach(function(it){
                var name = it.querySelector('.check-name'); var result = it.querySelector('.check-result');
                var remark = it.querySelector('.check-remark'); var skip = it.querySelector('.skip-reason');
                var skipDetail = it.querySelector('.skip-detail');
                dev.items.push({
                    name: name ? name.value : '',
                    result: result ? result.value : '',
                    remark: remark ? remark.value : '',
                    skip_reason: skip ? skip.value : '',
                    skip_detail: skipDetail ? skipDetail.value : '',
                });
            });
            devData.push(dev);
        });
        data['__devices__'] = devData;
        return data;
    }

    function saveDraft(){
        var data = snapshot();
        if (!data) return;
        var json = JSON.stringify(data);
        if (json === lastSavedHash) return;  // 无变化不保存
        setIndicator('正在保存草稿...', 'saving');
        fetch('/api/drafts/save', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({form_type: formType, related_id: relatedId, form_data_json: json}),
            credentials:'same-origin',
        })
        .then(function(r){ return r.json(); })
        .then(function(res){
            if (res.success) {
                lastSavedHash = json;
                var t = new Date();
                var hh = String(t.getHours()).padStart(2,'0'), mm = String(t.getMinutes()).padStart(2,'0'), ss = String(t.getSeconds()).padStart(2,'0');
                setIndicator('草稿已保存 ('+hh+':'+mm+':'+ss+')', 'ok');
            } else {
                setIndicator('保存失败: '+(res.error||'未知'), 'error');
            }
        })
        .catch(function(e){ setIndicator('保存失败: '+e, 'error'); });
    }

    function restoreDraft() {
        return fetch('/api/drafts/load?form_type='+encodeURIComponent(formType)+'&related_id='+relatedId, {credentials:'same-origin'})
            .then(function(r){ return r.json(); })
            .then(function(res){
                if (!res.success || !res.form_data_json || res.form_data_json === '{}') return false;
                var data;
                try { data = JSON.parse(res.form_data_json); } catch(e) { return false; }
                if (!data || Object.keys(data).length === 0) return false;
                var ts = res.updated_at ? new Date(res.updated_at).toLocaleString() : '未知';
                if (!confirm('检测到未保存的草稿（'+ts+'），是否恢复？\n\n点"取消"将放弃草稿继续填写空表。')) {
                    // 用户拒绝 → 删除草稿
                    fetch('/api/drafts/delete', {
                        method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body: JSON.stringify({form_type: formType, related_id: relatedId}),
                        credentials:'same-origin',
                    });
                    return false;
                }
                // 恢复表单字段
                applyDraft(data);
                return true;
            })
            .catch(function(){ return false; });
    }

    function applyDraft(data) {
        // 1. 原生字段
        var form = document.querySelector('form');
        if (!form) return;
        Object.keys(data).forEach(function(k){
            if (k === '__devices__') return;
            var els = form.querySelectorAll('[name="'+k+'"]');
            if (els.length === 0) return;
            if (els[0].type === 'checkbox' || els[0].type === 'radio') {
                var vals = Array.isArray(data[k]) ? data[k] : [data[k]];
                els.forEach(function(el){ el.checked = vals.indexOf(el.value) >= 0; });
            } else {
                els[0].value = data[k];
                // 触发 change 事件（让 onCustomerChange 等联动逻辑执行）
                els[0].dispatchEvent(new Event('change', {bubbles:true}));
            }
        });
        // 2. 设备区块——延迟应用，等设备卡片加载完
        var devData = data['__devices__'] || [];
        if (devData.length === 0) return;
        // 等设备卡片渲染完成（监听 devicesContainer 变化）
        var attempts = 0, maxAttempts = 20;
        var iv = setInterval(function(){
            attempts++;
            var cards = document.querySelectorAll('.device-item');
            if (cards.length === 0 && attempts < maxAttempts) return;
            clearInterval(iv);
            cards.forEach(function(card, idx){
                var dev = devData[idx]; if (!dev) return;
                Object.keys(dev.meta || {}).forEach(function(k){
                    var el = card.querySelector('[data-field="'+k+'"]');
                    if (el) el.value = dev.meta[k];
                });
                var items = card.querySelectorAll('.check-item, .check-row');
                (dev.items || []).forEach(function(it, j){
                    var iEl = items[j]; if (!iEl) return;
                    var n = iEl.querySelector('.check-name'); if (n && it.name) n.value = it.name;
                    var r = iEl.querySelector('.check-result'); if (r && it.result) { r.value = it.result; r.dispatchEvent(new Event('change',{bubbles:true})); }
                    var rm = iEl.querySelector('.check-remark'); if (rm && it.remark) rm.value = it.remark;
                    var sk = iEl.querySelector('.skip-reason'); if (sk && it.skip_reason) sk.value = it.skip_reason;
                    var skd = iEl.querySelector('.skip-detail'); if (skd && it.skip_detail) skd.value = it.skip_detail;
                });
            });
            setIndicator('已恢复草稿', 'ok');
        }, 500);
    }

    // 输入时延迟保存（5s 防抖），整体每 30s 强制保存
    function scheduleSave(){
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(saveDraft, 5000);
    }

    // 页面加载完后：先尝试恢复，再启动定时器
    function init(){
        restoreDraft().finally(function(){
            // 监听整个表单输入
            document.addEventListener('input', scheduleSave, true);
            document.addEventListener('change', scheduleSave, true);
            // 每 30s 强制保存一次
            setInterval(saveDraft, 30000);
            // 离开页面前最后一次保存
            window.addEventListener('beforeunload', function(){
                // 同步使用 sendBeacon 保证发出
                if (navigator.sendBeacon) {
                    var json = JSON.stringify(snapshot() || {});
                    if (json !== lastSavedHash) {
                        var blob = new Blob([JSON.stringify({form_type: formType, related_id: relatedId, form_data_json: json})], {type:'application/json'});
                        navigator.sendBeacon('/api/drafts/save', blob);
                    }
                }
            });
        });
    }

    // 提交成功后清理（saveInspection 会调用此函数）
    window._draftDeleteOnSubmit = function(){
        if (navigator.sendBeacon) {
            var blob = new Blob([JSON.stringify({form_type: formType, related_id: relatedId})], {type:'application/json'});
            navigator.sendBeacon('/api/drafts/delete', blob);
        } else {
            fetch('/api/drafts/delete', {method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({form_type: formType, related_id: relatedId}), credentials:'same-origin', keepalive:true});
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
// ====== END 草稿自动保存 ======
