/**
 * dropdown-portal.js
 *
 * 把带有 .js-dropdown-portal 标记的 Bootstrap 5 下拉菜单临时挪到 <body> 下，
 * 避免被父级容器 overflow:auto/hidden 裁切（典型场景：看板卡片、列表行操作列）。
 *
 * 用法：
 *   1) 给 <button data-bs-toggle="dropdown"> 上加 class="js-dropdown-portal"
 *      （或加在外层 .dropdown 容器上也可；最终找紧邻的 .dropdown-menu）
 *   2) 引入本脚本（base.html 已统一加载）
 *
 * 工作原理：
 *   show.bs.dropdown    → 把 .dropdown-menu append 到 document.body，用 fixed 定位到 toggle 旁
 *   hidden.bs.dropdown  → 把菜单放回原 placeholder
 *   resize / scroll(capture) 时实时重定位，保证菜单贴着 toggle
 */
(function () {
    'use strict';

    var PORTAL_CLASS = 'js-dropdown-portal-active';
    var PLACEHOLDER_ATTR = 'data-dropdown-portal-id';
    var seq = 0;
    var activeMenus = []; // [{menu, toggle, placeholder, parent}]

    function isPortalToggle(el) {
        if (!el) return false;
        return el.classList && (
            el.classList.contains('js-dropdown-portal') ||
            (el.closest && el.closest('.js-dropdown-portal'))
        );
    }

    function findMenu(toggle) {
        // 优先找紧邻兄弟里的 .dropdown-menu
        var parent = toggle.parentElement;
        if (!parent) return null;
        var menu = parent.querySelector(':scope > .dropdown-menu');
        if (menu) return menu;
        // 再退到 closest('.dropdown') 容器里找
        var dd = toggle.closest('.dropdown, .dropup, .dropstart, .dropend');
        if (dd) return dd.querySelector(':scope > .dropdown-menu');
        return null;
    }

    function positionMenu(toggle, menu) {
        var rect = toggle.getBoundingClientRect();
        var menuRect = menu.getBoundingClientRect();
        var vw = window.innerWidth;
        var vh = window.innerHeight;

        // 默认放在 toggle 下方右对齐（与 dropdown-menu-end 行为一致）
        var alignEnd = menu.classList.contains('dropdown-menu-end');
        var top = rect.bottom + 2;
        var left = alignEnd ? (rect.right - menuRect.width) : rect.left;

        // 下方不够 → 翻到上方
        if (top + menuRect.height > vh - 4 && rect.top - menuRect.height - 2 > 0) {
            top = rect.top - menuRect.height - 2;
        }
        // 左右边界保护
        if (left < 4) left = 4;
        if (left + menuRect.width > vw - 4) left = vw - menuRect.width - 4;
        if (top < 4) top = 4;

        menu.style.position = 'fixed';
        menu.style.top = top + 'px';
        menu.style.left = left + 'px';
        menu.style.right = 'auto';
        menu.style.bottom = 'auto';
        menu.style.transform = 'none';
        menu.style.margin = '0';
    }

    function repositionAll() {
        for (var i = 0; i < activeMenus.length; i++) {
            var rec = activeMenus[i];
            if (rec.menu.classList.contains('show')) {
                positionMenu(rec.toggle, rec.menu);
            }
        }
    }

    document.addEventListener('show.bs.dropdown', function (e) {
        var toggle = e.target;
        if (!isPortalToggle(toggle)) return;
        var menu = findMenu(toggle);
        if (!menu) return;

        var parent = menu.parentElement;
        if (!parent || parent === document.body) return;

        // 留一个占位符，hidden 时放回原位
        var id = 'dpp-' + (++seq);
        var placeholder = document.createComment('dropdown-portal:' + id);
        menu.setAttribute(PLACEHOLDER_ATTR, id);
        parent.insertBefore(placeholder, menu);
        document.body.appendChild(menu);
        menu.classList.add(PORTAL_CLASS);

        activeMenus.push({
            menu: menu,
            toggle: toggle,
            placeholder: placeholder,
            parent: parent,
            id: id,
        });

        // Bootstrap 在 show.bs.dropdown 之后才把 .show 加到 menu；下一帧定位
        window.requestAnimationFrame(function () {
            positionMenu(toggle, menu);
        });
    });

    document.addEventListener('hidden.bs.dropdown', function (e) {
        var toggle = e.target;
        if (!isPortalToggle(toggle)) return;
        var menu = findMenu(toggle);
        if (!menu) return;

        var id = menu.getAttribute(PLACEHOLDER_ATTR);
        if (!id) return;

        // 找出对应 record，放回原位
        for (var i = activeMenus.length - 1; i >= 0; i--) {
            var rec = activeMenus[i];
            if (rec.id === id) {
                if (rec.placeholder && rec.placeholder.parentNode) {
                    rec.placeholder.parentNode.insertBefore(menu, rec.placeholder);
                    rec.placeholder.parentNode.removeChild(rec.placeholder);
                } else if (rec.parent) {
                    rec.parent.appendChild(menu);
                }
                menu.classList.remove(PORTAL_CLASS);
                menu.removeAttribute(PLACEHOLDER_ATTR);
                // 还原内联样式
                menu.style.position = '';
                menu.style.top = '';
                menu.style.left = '';
                menu.style.right = '';
                menu.style.bottom = '';
                menu.style.transform = '';
                menu.style.margin = '';
                activeMenus.splice(i, 1);
                break;
            }
        }
    });

    // 滚动/resize 时跟随 toggle 重定位（捕获阶段才能拦到内层滚动容器）
    window.addEventListener('scroll', repositionAll, true);
    window.addEventListener('resize', repositionAll);
})();
