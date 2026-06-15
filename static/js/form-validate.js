/* 通用表单验证工具 v1 — 由 base.html 引入 */

/**
 * 校验单个表单
 * @param {HTMLFormElement} form
 * @param {Object} rules - { fieldName: { required, min, max, pattern, label } }
 * @returns {boolean} true=通过; false=有错误
 */
function validateForm(form, rules) {
    // 清除旧错误
    form.querySelectorAll('.is-invalid').forEach(function(el){ el.classList.remove('is-invalid'); });
    form.querySelectorAll('.invalid-feedback').forEach(function(el){ el.remove(); });
    var ok = true;
    var firstBad = null;
    Object.keys(rules).forEach(function(name) {
        var rule = rules[name];
        var el = form.querySelector('[name="' + name + '"]');
        if (!el) return;
        var val = (el.value || '').trim();
        var label = rule.label || name;
        var err = null;
        if (rule.required && val === '') {
            err = label + '不能为空';
        } else if (rule.min != null && val !== '' && parseFloat(val) < rule.min) {
            err = label + '不能小于 ' + rule.min;
        } else if (rule.max != null && val !== '' && parseFloat(val) > rule.max) {
            err = label + '不能大于 ' + rule.max;
        } else if (rule.minLen != null && val.length < rule.minLen) {
            err = label + '至少 ' + rule.minLen + ' 个字符';
        } else if (rule.maxLen != null && val.length > rule.maxLen) {
            err = label + '最多 ' + rule.maxLen + ' 个字符';
        } else if (rule.pattern && val !== '' && !rule.pattern.test(val)) {
            err = rule.patternMsg || (label + '格式不正确');
        }
        if (err) {
            ok = false;
            el.classList.add('is-invalid');
            var fb = document.createElement('div');
            fb.className = 'invalid-feedback';
            fb.textContent = err;
            el.parentNode.appendChild(fb);
            if (!firstBad) firstBad = el;
        }
    });
    if (firstBad) firstBad.focus();
    return ok;
}

/**
 * 通用确认弹窗（替代 window.confirm）
 */
function confirmAction(message) {
    return window.confirm(message || '确定执行此操作？');
}

/**
 * 数字输入框：自动限制为非负整数
 */
function setupNumberInputs() {
    document.querySelectorAll('input[type="number"]').forEach(function(el) {
        el.addEventListener('keydown', function(e) {
            // 允许: 退格、删除、tab、escape、enter、方向键、小数点
            if ([46, 8, 9, 27, 13, 110, 190].indexOf(e.keyCode) !== -1 ||
                (e.keyCode === 65 && e.ctrlKey) ||  // Ctrl+A
                (e.keyCode >= 35 && e.keyCode <= 40)) {  // 方向键
                return;
            }
            if ((e.shiftKey || (e.keyCode < 48 || e.keyCode > 57)) && (e.keyCode < 96 || e.keyCode > 105)) {
                e.preventDefault();
            }
        });
    });
}
document.addEventListener('DOMContentLoaded', setupNumberInputs);
