# -*- coding: utf-8 -*-
"""备件管理蓝图：备件档案 / 库存 / 采购入库 / 销售出库

写操作统一走 utils.decorators.form_commit（try/except/rollback/flash/redirect 封装）。
"""
import os
import uuid
from datetime import date
from flask import (Blueprint, render_template, request,
                   send_from_directory, flash, redirect, url_for)
from flask_login import login_required, current_user
from models import (SparePart, SpareStock, PurchaseOrder, SalesOrder, Customer, db)
from services.spare_service import (
    create_spare_part, update_spare_part, delete_spare_part,
    create_purchase_order, create_sales_order,
    delete_purchase_order, delete_sales_order,
)
from utils.decorators import form_commit
from utils.permission import require_permission

spare_bp = Blueprint('spare', __name__)

# V6 备件图片保存目录（目录由 create_app 的 _ensure_runtime_dirs 统一创建，消除导入副作用）
SPARE_IMG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'static', 'uploads', 'spare_parts')

# 允许的图片扩展名
ALLOWED_IMG_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}


def _save_spare_image(file_storage, spare_id):
    """保存备件图片到 static/uploads/spare_parts/<spare_id>/<filename>，返回相对 static 路径"""
    if not file_storage or not file_storage.filename:
        return ''
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_IMG_EXTS:
        return ''
    # 用 UUID 防止文件名冲突
    safe_name = f'{uuid.uuid4().hex}{ext}'
    sub_dir = os.path.join(SPARE_IMG_DIR, str(spare_id))
    os.makedirs(sub_dir, exist_ok=True)
    full_path = os.path.join(sub_dir, safe_name)
    file_storage.save(full_path)
    # 返回相对 static 的路径
    return f'uploads/spare_parts/{spare_id}/{safe_name}'


def _me():
    return current_user.realname or current_user.username


# ============================ 备件档案 ============================
@spare_bp.route('/spare-parts')
@login_required
@require_permission('spare:view')
def spare_part_list():
    parts = SparePart.query.order_by(SparePart.id.desc()).all()
    # 序列化为 dict 以便模板中传给 JS 的 tojson
    p_dicts = [{
        'id': p.id, 'code': p.code, 'name': p.name, 'unit': p.unit,
        'brand': p.brand, 'model': p.model, 'manufacturer': p.manufacturer,
        'category': p.category, 'specification': p.specification,
        'min_stock': p.min_stock, 'parameters': p.parameters,
        'reference_price': p.reference_price, 'warranty_months': p.warranty_months,
        'serial_number': p.serial_number, 'image_path': p.image_path, 'remark': p.remark,
    } for p in parts]
    return render_template('spare_parts/list.html', parts=parts, p_dicts=p_dicts)


@spare_bp.route('/spare-parts/add', methods=['POST'])
@login_required
@require_permission('spare:add')
@form_commit(lambda sp: f'备件 "{sp.name}" 已添加', 'spare.spare_part_list', '备件添加失败')
def spare_part_add():
    sp = create_spare_part(request.form.to_dict())
    db.session.commit()  # 立即提交以获取 ID
    # 处理图片上传
    img_path = _save_spare_image(request.files.get('image'), sp.id)
    if img_path:
        sp.image_path = img_path
        db.session.commit()
    return sp


@spare_bp.route('/spare-parts/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('spare:edit')
@form_commit('已更新', 'spare.spare_part_list', '备件更新失败')
def spare_part_edit(id):
    # 处理图片上传（先于 update）
    sp = SparePart.query.get_or_404(id)
    new_img = request.files.get('image')
    data = request.form.to_dict()
    if new_img and new_img.filename:
        img_path = _save_spare_image(new_img, sp.id)
        if img_path:
            data['image_path'] = img_path
    update_spare_part(id, data)


@spare_bp.route('/spare-parts/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('spare:delete')
@form_commit('已删除', 'spare.spare_part_list', '备件删除失败')
def spare_part_delete(id):
    delete_spare_part(id)


@spare_bp.route('/spare-parts/<int:id>')
@login_required
@require_permission('spare:view')
def spare_part_detail(id):
    """备件详情页：完整档案 + 图片 + 关联库存/采购/销售记录"""
    sp = SparePart.query.get_or_404(id)
    stocks = SpareStock.query.filter_by(spare_part_id=id).order_by(SpareStock.id.desc()).all()
    purchases = PurchaseOrder.query.filter_by(spare_part_id=id).order_by(PurchaseOrder.id.desc()).limit(20).all()
    sales = SalesOrder.query.filter_by(spare_part_id=id).order_by(SalesOrder.id.desc()).limit(20).all()
    return render_template('spare_parts/detail.html',
                           sp=sp, stocks=stocks, purchases=purchases, sales=sales)


@spare_bp.route('/spare-parts/export')
@login_required
@require_permission('spare:view')
def spare_export():
    """导出备件档案到 Excel（统一走 utils.excel_export，绿色表头）"""
    from utils.excel_export import export_xlsx
    headers = ['编码', '名称', '品牌', '型号', '厂家', '分类', '规格', '参数',
               '单位', '参考价', '保修期(月)', '最低库存', '序列号', '备注']
    rows = [[p.code, p.name, p.brand, p.model, p.manufacturer,
             p.category, p.specification, p.parameters,
             p.unit, p.reference_price, p.warranty_months,
             p.min_stock, p.serial_number, p.remark]
            for p in SparePart.query.order_by(SparePart.id).all()]
    path, download_name = export_xlsx(
        headers, rows, f'备件档案_{date.today().isoformat()}.xlsx',
        sheet_name='备件档案', header_color=('52C41A', '389E0D'))
    return send_from_directory(os.path.dirname(path), os.path.basename(path),
                               as_attachment=True, download_name=download_name)


# ============================ 库存 ============================
@spare_bp.route('/spare-stocks')
@login_required
@require_permission('spare:view')
def spare_stock_list():
    stocks = SpareStock.query.order_by(SpareStock.id.desc()).all()
    parts = SparePart.query.order_by(SparePart.name).all()
    return render_template('spare_stocks/list.html', stocks=stocks, parts=parts)


@spare_bp.route('/spare-stocks/add', methods=['POST'])
@login_required
@require_permission('spare:add')
@form_commit('库存已添加', 'spare.spare_stock_list', '库存添加失败')
def spare_stock_add():
    qty = int(request.form.get('quantity', 0))
    if qty < 0:
        raise ValueError('库存数量不能为负数')
    ss = SpareStock(
        spare_part_id=int(request.form['spare_part_id']),
        location=request.form.get('location', ''),
        quantity=qty,
        unit_price=float(request.form.get('unit_price', 0)),
    )
    db.session.add(ss)
    db.session.commit()


@spare_bp.route('/spare-stocks/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('spare:edit')
def spare_stock_edit(id):
    ss = SpareStock.query.get_or_404(id)
    qty = int(request.form.get('quantity', 0))
    if qty < 0:
        flash('库存数量不能为负数', 'danger')
        return redirect(url_for('spare.spare_stock_list'))
    ss.quantity = qty
    ss.location = request.form.get('location', '')
    ss.unit_price = float(request.form.get('unit_price', 0))
    db.session.commit()
    flash('已更新', 'success')
    return redirect(url_for('spare.spare_stock_list'))


@spare_bp.route('/spare-stocks/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('spare:delete')
@form_commit('已删除', 'spare.spare_stock_list', '库存删除失败')
def spare_stock_delete(id):
    ss = SpareStock.query.get_or_404(id)
    db.session.delete(ss)
    db.session.commit()


# ============================ 采购入库 ============================
@spare_bp.route('/purchase-orders')
@login_required
@require_permission('spare:view')
def purchase_order_list():
    orders = PurchaseOrder.query.order_by(PurchaseOrder.id.desc()).all()
    parts = SparePart.query.order_by(SparePart.name).all()
    return render_template('purchase_orders/list.html', orders=orders, parts=parts)


@spare_bp.route('/purchase-orders/add', methods=['POST'])
@login_required
@require_permission('spare:add')
@form_commit('采购单已创建', 'spare.purchase_order_list', '采购单创建失败')
def purchase_order_add():
    create_purchase_order(request.form.to_dict(), _me())


@spare_bp.route('/purchase-orders/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('spare:delete')
@form_commit('已删除', 'spare.purchase_order_list', '采购单删除失败')
def purchase_order_delete(id):
    delete_purchase_order(id)


# ============================ 销售出库 ============================
@spare_bp.route('/sales-orders')
@login_required
@require_permission('spare:view')
def sales_order_list():
    orders = SalesOrder.query.order_by(SalesOrder.id.desc()).all()
    parts = SparePart.query.order_by(SparePart.name).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('sales_orders/list.html', orders=orders, parts=parts, customers=customers)


@spare_bp.route('/sales-orders/add', methods=['POST'])
@login_required
@require_permission('spare:add')
@form_commit('销售单已创建', 'spare.sales_order_list', '销售单创建失败')
def sales_order_add():
    create_sales_order(request.form.to_dict(), _me())


@spare_bp.route('/sales-orders/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('spare:delete')
@form_commit('已删除', 'spare.sales_order_list', '销售单删除失败')
def sales_order_delete(id):
    delete_sales_order(id)
