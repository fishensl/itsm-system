"""分页工具"""
from math import ceil


def paginate(query, page=1, per_page=20):
    """手动分页查询，返回分页结果字典"""
    page = max(1, int(page) if page else 1)
    per_page = max(1, min(100, int(per_page) if per_page else 20))

    total = query.count()
    total_pages = max(1, ceil(total / per_page))
    page = min(page, total_pages)

    items = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        'items': items,
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
    }


def paginate_render_args(pag):
    """返回模板渲染用的分页信息"""
    return {
        'items': pag['items'],
        'page': pag['page'],
        'per_page': pag['per_page'],
        'total': pag['total'],
        'total_pages': pag['total_pages'],
        'has_prev': pag['has_prev'],
        'has_next': pag['has_next'],
        'prev_page': pag['page'] - 1 if pag['has_prev'] else None,
        'next_page': pag['page'] + 1 if pag['has_next'] else None,
        'start': (pag['page'] - 1) * pag['per_page'] + 1 if pag['total'] > 0 else 0,
        'end': min(pag['page'] * pag['per_page'], pag['total']),
    }
