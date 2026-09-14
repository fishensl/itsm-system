"""客户群通知继承：父级允许共用 + 子级可关，摘要同步聚合。"""
from datetime import datetime

from models import db, Customer, CustomerNotifyBinding, NotificationDelivery, NotificationEvent
from services import customer_notify_service as service
from services import notification_worker as worker
from services.notification_outbox import insert_event

PARENT_URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=inherit-parent'
CHILD_URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=inherit-child'


def _family():
    parent = Customer(name='景德镇城防')
    db.session.add(parent)
    db.session.flush()
    child = Customer(name='景德镇城防排涝站', parent_id=parent.id)
    db.session.add(child)
    db.session.commit()
    return parent.id, child.id


def _event(customer_id, key, kind='inspection_started'):
    return insert_event(db.session.connection(), kind, {'title': '任务', 'content': '内容'},
                        customer_id=customer_id, entity_type='', entity_id=None, key=key)


def test_child_inherits_shared_parent_binding(app):
    with app.app_context():
        parent_id, child_id = _family()
        service.save_binding(parent_id, PARENT_URL, True, inherit_to_children=True,
                             subscriptions={'inspection_started': True})
        info = service.settings(child_id)['inherited_from']
        assert info and info['customer_id'] == parent_id and info['name'] == '客户群'
        event_id = _event(child_id, 'inherit-1')
        delivery = NotificationDelivery.query.filter_by(event_id=event_id).one()
        binding = CustomerNotifyBinding.query.filter_by(customer_id=parent_id).one()
        assert delivery.binding_id == binding.id
        assert delivery.binding_version == binding.version
        event = db.session.get(NotificationEvent, event_id)
        assert worker.valid_destination(delivery, event, binding) == ''


def test_inherit_requires_parent_share_and_child_optin(app):
    with app.app_context():
        parent_id, child_id = _family()
        service.save_binding(parent_id, PARENT_URL, True, inherit_to_children=False,
                             subscriptions={'inspection_started': True})
        e1 = _event(child_id, 'off-1')
        assert NotificationDelivery.query.filter_by(event_id=e1).count() == 0

        service.save_binding(parent_id, '', True, inherit_to_children=True)
        e2 = _event(child_id, 'on-1')
        delivery = NotificationDelivery.query.filter_by(event_id=e2).one()

        service.save_inherit_parent(child_id, False)
        e3 = _event(child_id, 'off-2')
        assert NotificationDelivery.query.filter_by(event_id=e3).count() == 0
        # 已入队的继承投递在发送前复核会被取消
        event = db.session.get(NotificationEvent, e2)
        binding = CustomerNotifyBinding.query.filter_by(customer_id=parent_id).one()
        assert worker.valid_destination(delivery, event, binding) == 'binding_changed'


def test_own_binding_takes_priority_and_disabled_does_not_fallback(app):
    with app.app_context():
        parent_id, child_id = _family()
        service.save_binding(parent_id, PARENT_URL, True, inherit_to_children=True,
                             subscriptions={'inspection_started': True})
        service.save_binding(child_id, CHILD_URL, True, subscriptions={'inspection_started': True})
        e1 = _event(child_id, 'own-1')
        child_binding = CustomerNotifyBinding.query.filter_by(customer_id=child_id).one()
        assert NotificationDelivery.query.filter_by(event_id=e1).one().binding_id == child_binding.id

        service.save_binding(child_id, '', False)
        e2 = _event(child_id, 'disabled-1')
        assert NotificationDelivery.query.filter_by(event_id=e2).count() == 0

        draft = Customer(name='无群下级', parent_id=parent_id)
        db.session.add(draft)
        db.session.commit()
        service.save_binding(draft.id, '', False)  # 空草稿（无 webhook）不阻止继承
        e3 = _event(draft.id, 'draft-1')
        parent_binding = CustomerNotifyBinding.query.filter_by(customer_id=parent_id).one()
        assert NotificationDelivery.query.filter_by(event_id=e3).one().binding_id == parent_binding.id


def test_digest_aggregates_inherited_children(app):
    with app.app_context():
        parent_id, child_id = _family()
        service.save_binding(parent_id, PARENT_URL, True, inherit_to_children=True,
                             subscriptions={'ticket_completed': True, 'customer_digest': True})
        insert_event(db.session.connection(), 'ticket_completed', {'title': '工单', 'content': '完成'},
                     customer_id=parent_id, key='digest-parent')
        insert_event(db.session.connection(), 'ticket_completed', {'title': '工单', 'content': '完成'},
                     customer_id=child_id, key='digest-child')
        db.session.commit()
        from services.notification_jobs import periodic
        periodic(datetime(2026, 9, 14, 2))
        digest = NotificationEvent.query.filter_by(event_type='customer_digest').one()
        assert digest.customer_id == parent_id
        assert '2 项服务成果' in digest.payload_json


def test_inherit_api_and_binding_share_switch(admin_client, app):
    with app.app_context():
        parent_id, child_id = _family()
    result = admin_client.put(f'/api/customers/{child_id}/notify-inherit',
                              json={'inherit_parent': False})
    assert result.status_code == 200, result.get_json()
    assert result.get_json()['data']['notify_inherit_parent'] is False
    assert admin_client.put(f'/api/customers/{child_id}/notify-inherit',
                            json={'inherit_parent': 'yes'}).status_code == 400

    result = admin_client.put(f'/api/customers/{parent_id}/notify-webhook',
                              json={'wecom_webhook': PARENT_URL, 'notify_enabled': True,
                                    'inherit_to_children': True})
    assert result.status_code == 200, result.get_json()
    binding = result.get_json()['data']['bindings'][0]
    assert binding['inherit_to_children'] is True
    assert result.get_json()['data']['notify_inherit_parent'] is True
