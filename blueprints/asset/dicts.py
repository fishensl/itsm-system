# -*- coding: utf-8 -*-
"""设备字典配置（工厂生成：设备类型/品牌/网络类型/自定义字段）"""
from flask import (render_template, request, redirect, url_for,
                   flash)
from flask_login import login_required
from models import (db, DeviceType, Brand,
                    NetworkType, CustomField)
from utils.permission import require_permission
from blueprints.asset import asset_bp


# ============================ 设备字典配置（工厂生成：设备类型/品牌/网络类型/自定义字段） ============================
def register_dict_crud(bp, *, path, model, template, list_var, endpoint_prefix,
                       order='sort', extra_fields=()):
    """注册字典配置 CRUD 路由（替代原四份同构复制代码）。

    path: URL 前缀（如 '/device-types'）；model: 需有 name 字段的 ORM 模型
    order: 'sort' 按 sort_order+id，'id' 仅按 id
    extra_fields: add/edit 时从表单透传的额外字段（如 ('field_type',)）
    生成端点名与原手工路由完全一致（list/edit/delete/add），模板 url_for 不受影响。
    """
    list_ep = f'{endpoint_prefix}_list'
    sort_cols = (model.sort_order, model.id) if order == 'sort' else (model.id,)

    def _apply_form(obj, is_new):
        """表单值落模型；新增时 name 必填（返回 False 表示校验失败）"""
        name = (request.form.get('name') or '').strip()
        if name:
            obj.name = name
        elif is_new:
            return False
        if hasattr(model, 'sort_order') and request.form.get('sort_order') is not None:
            obj.sort_order = int(request.form.get('sort_order') or 0)
        for f in extra_fields:
            v = request.form.get(f)
            if v is not None:
                setattr(obj, f, v)
        return True

    def _do_add():
        obj = model()
        if _apply_form(obj, is_new=True):
            db.session.add(obj)
            db.session.commit()
            flash('已添加', 'success')
        return redirect(url_for(f'asset.{list_ep}'))

    @login_required
    @require_permission('device:view')
    def list_view():
        if request.method == 'POST':
            return _do_add()
        items = model.query.order_by(*sort_cols).all()
        return render_template(template, **{list_var: items})

    @login_required
    @require_permission('device:edit')
    def edit_view(id):
        obj = model.query.get_or_404(id)
        _apply_form(obj, is_new=False)
        db.session.commit()
        flash('已更新', 'success')
        return redirect(url_for(f'asset.{list_ep}'))

    @login_required
    @require_permission('device:delete')
    def delete_view(id):
        model.query.filter_by(id=id).delete()
        db.session.commit()
        flash('已删除', 'success')
        return redirect(url_for(f'asset.{list_ep}'))

    @login_required
    @require_permission('device:edit')
    def add_view():
        return _do_add()

    bp.add_url_rule(path, endpoint_prefix + '_list', list_view, methods=['GET', 'POST'])
    bp.add_url_rule(f'{path}/edit/<int:id>', endpoint_prefix + '_edit', edit_view, methods=['POST'])
    bp.add_url_rule(f'{path}/delete/<int:id>', endpoint_prefix + '_delete', delete_view, methods=['POST'])
    bp.add_url_rule(f'{path}/add', endpoint_prefix + '_add', add_view, methods=['POST'])


register_dict_crud(asset_bp, path='/device-types', model=DeviceType,
                   template='device_types/list.html', list_var='types',
                   endpoint_prefix='device_type')
register_dict_crud(asset_bp, path='/device-brands', model=Brand,
                   template='brands/list.html', list_var='brands',
                   endpoint_prefix='brand')
register_dict_crud(asset_bp, path='/device-network-types', model=NetworkType,
                   template='network_types/list.html', list_var='types',
                   endpoint_prefix='network_type', order='id')
register_dict_crud(asset_bp, path='/device-custom-fields', model=CustomField,
                   template='custom_fields/list.html', list_var='fields',
                   endpoint_prefix='custom_field', order='id',
                   extra_fields=('field_type',))


