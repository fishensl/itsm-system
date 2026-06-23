/**
 * theme.js - 公共主题切换逻辑
 *
 * 同时被 base.html（含侧边栏的全站页面）和 login.html 引用，
 * 避免两边重复实现。注意：首屏防闪烁的内联 attribute 设置需要在
 * 各页面的 <head> 顶部单独保留（不能依赖此外部脚本，否则有白闪窗口）。
 *
 * 暴露全局函数：
 *   applyTheme(theme)  - 设置主题并同步 UI 与 localStorage
 *   toggleTheme()      - 在 light / dark 之间切换
 * 派发自定义事件：
 *   document 上的 'themechange'，detail: { theme }
 */
(function () {
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.setAttribute('data-bs-theme', theme);
        try { localStorage.setItem('appTheme', theme); } catch (e) {}
        var icon = document.getElementById('themeToggleIcon');
        var text = document.getElementById('themeToggleText');
        if (icon) icon.className = theme === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
        if (text) text.textContent = theme === 'dark' ? '浅色模式' : '深色模式';
        document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
    }

    function toggleTheme() {
        var t = document.documentElement.getAttribute('data-theme') || 'light';
        applyTheme(t === 'dark' ? 'light' : 'dark');
    }

    window.applyTheme = applyTheme;
    window.toggleTheme = toggleTheme;

    // DOM 就绪后再同步一次图标/文案（首屏 attribute 已通过页面内联脚本设好，
    // 此处只补齐图标/文案，无 attribute 变化也不会重复派发事件）
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            var t = document.documentElement.getAttribute('data-theme') || 'light';
            var icon = document.getElementById('themeToggleIcon');
            var text = document.getElementById('themeToggleText');
            if (icon) icon.className = t === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
            if (text) text.textContent = t === 'dark' ? '浅色模式' : '深色模式';
        });
    }
})();
