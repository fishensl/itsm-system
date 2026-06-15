/**
 * 合并面包屑 + 筛选栏 + 操作按钮到单行
 *
 * 目标：把顶部"面包屑"+"筛选栏"+"操作按钮"三段合并为一行内的多段式布局
 *
 * 流程：
 *   1) 取出 .page-toolbar 内的 .actions，挂到 .breadcrumb-nav 末尾
 *   2) 移除 .page-toolbar 容器
 *   3) 把 .filter-bar 内 .card-body 下的 <form>/<子元素> 拆出，直接挂到 .breadcrumb-nav
 *      （避免 .card-body 残留 padding/margin 干扰行内布局）
 *   4) 把 .breadcrumb-nav 内 actions 之前的所有直接子元素包成 .breadcrumb-path
 *      （让 .breadcrumb-nav 的 flex 布局只在 path / filter / actions 三段之间生效）
 *
 * 结果结构（有筛选+操作）：
 *   <div class="breadcrumb-nav">
 *     <div class="breadcrumb-path">...面包屑链接/分隔符...</div>
 *     <div class="filter-bar">...筛选表单...</div>
 *     <div class="actions">...操作按钮...</div>
 *   </div>
 *
 * 结果结构（仅面包屑，e.g. 报告管理）：
 *   <div class="breadcrumb-nav">
 *     <div class="breadcrumb-path">...面包屑链接/分隔符...</div>
 *   </div>
 */
(function mergeTopRow() {
    // 1) 合并 toolbar
    document.querySelectorAll('.breadcrumb-nav + .page-toolbar').forEach(function (tb) {
        var nav = tb.previousElementSibling;
        if (!nav || !nav.classList.contains('breadcrumb-nav')) return;
        var actions = tb.querySelector('.actions');
        if (actions) {
            nav.appendChild(actions);
        }
        tb.parentNode.removeChild(tb);
    });

    // 2) 处理 .filter-bar：拆掉 .card-body 外壳，把内容挂到面包屑行内
    //    兼容嵌套：filter-bar 可能在 .content-card / 其他容器内，目标是文档中第一个 .breadcrumb-nav
    var firstNav = document.querySelector('.breadcrumb-nav');
    if (!firstNav) return; // 没有面包屑行，不处理

    document.querySelectorAll('.filter-bar').forEach(function (bar) {
        // 跳过内层的 <form class="filter-bar">——它们没有 .card-body / .card 父级
        if (bar.tagName === 'FORM') return;

        // 把 .card-body（若有）拆开：form/子元素直接作为 .filter-bar 的子元素
        var cardBody = bar.querySelector('.card-body');
        if (cardBody) {
            while (cardBody.firstChild) {
                bar.insertBefore(cardBody.firstChild, cardBody);
            }
            cardBody.remove();
        }
        // 去除 filter-bar 上的 card mb-3 样式残留
        bar.classList.remove('card', 'mb-3');

        // 把 .filter-bar 整体挂到 .breadcrumb-nav（在 .actions 之前）
        var actions = firstNav.querySelector(':scope > .actions');
        if (actions) {
            firstNav.insertBefore(bar, actions);
        } else {
            firstNav.appendChild(bar);
        }
    });

    // 3) 把 .breadcrumb-nav 内 .actions / .filter-bar 之前的所有直接子元素包成 .breadcrumb-path
    document.querySelectorAll('.breadcrumb-nav').forEach(function (nav) {
        if (nav.querySelector(':scope > .breadcrumb-path')) return; // 已处理

        var actions = nav.querySelector(':scope > .actions');
        var path = document.createElement('div');
        path.className = 'breadcrumb-path';
        while (nav.firstChild && nav.firstChild !== actions) {
            path.appendChild(nav.firstChild);
        }
        if (actions) {
            nav.insertBefore(path, actions);
        } else if (path.firstChild) {
            nav.appendChild(path);
        }
    });
})();
