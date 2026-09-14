from datetime import date, datetime, timedelta
import pytest
from models import db, User, Customer, Ticket, InspectionTask, NotificationEvent as Event, NotificationDelivery as Delivery, NotificationPreference, NotifyChannelConfig, Department
from services import notification_policy as policy, notification_management as management
from services.notification_jobs import periodic
from services.notification_outbox import insert_event, queue_internal
from services.base import ServiceError
from utils import constants as C
from utils.json_fields import parse_json


def test_policy_validates_active_recipients_and_range(app):
    with app.app_context():
        with pytest.raises(ServiceError):
            policy.save(policy.DEFAULTS | {'hour': 24})
        with pytest.raises(ServiceError):
            policy.save(policy.DEFAULTS | {'extra_user_ids': [999999]})
        policy.save(policy.DEFAULTS | {'escalation_days': 2})
        assert policy.current()['escalation_days'] == 2


def test_ticket_escalation_and_full_digest(app):
    with app.app_context():
        admin = User.query.filter_by(username='admin').one()
        op = User.query.filter_by(username='op').one()
        dept = Department(name='通知测试部门', head_id=admin.id); db.session.add(dept); db.session.flush()
        op.department_id = dept.id
        customer = Customer(name='提醒客户'); db.session.add(customer); db.session.flush()
        from models import customer_engineers
        db.session.execute(customer_engineers.insert().values(customer_id=customer.id, engineer_id=op.id))
        ticket = Ticket(number='REM-001', title='逾期', customer_id=customer.id, assigned_to=op.username, status=C.TICKET_PROCESSING, sla_deadline=datetime(2026, 9, 1))
        db.session.add(ticket)
        db.session.add(NotificationPreference(user_id=op.id, daily_digest=True, weekly_digest=False, reminders=True))
        db.session.commit()
        periodic(datetime(2026, 9, 12, 2)); periodic(datetime(2026, 9, 12, 2))
        escalation = Event.query.filter_by(event_type='reminder_escalation', entity_type='ticket').all()
        assert len(escalation) == 1
        assert Delivery.query.filter_by(event_id=escalation[0].id).one().user_id == admin.id
        text = parse_json(Event.query.filter_by(event_type='personal_digest').one().payload_json, default={})['content']
        assert '工单待办 1' in text and '通知失败/未知' in text and '逾期 1' in text


def test_metrics_scope_and_duration(app):
    with app.app_context():
        admin = User.query.filter_by(username='admin').one()
        eid = insert_event(db.session.connection(), 'security_event', {}, audience='internal', targets=[{'target_key':'test','channel_type':'wecom'}])
        db.session.commit()
        event = db.session.get(Event, eid); row = Delivery.query.one()
        row.status = 'accepted'; row.finished_at = event.created_at + timedelta(seconds=12)
        db.session.commit()
        result = management.metrics(admin)
        assert result['average_delivery_seconds'] == 12
        assert result['by_channel'] == [{'key':'wecom','status':'accepted','count':1}]


def test_explicit_transactional_queue_does_not_commit(app):
    with app.app_context():
        admin = User.query.filter_by(username='admin').one()
        db.session.add(NotifyChannelConfig(channel_type='wecom', config_json='{}', is_enabled=True)); db.session.commit()
        queue_internal('security_event','test',user_ids=[admin.id],commit=False)
        assert Event.query.count() == 1
        db.session.rollback()
        assert Event.query.count() == 0


def test_policy_api_permissions_and_mfa(admin_client, viewer_client, monkeypatch):
    assert viewer_client.put('/api/notification-policy', json=policy.DEFAULTS).status_code == 403
    assert admin_client.put('/api/notification-policy', json=policy.DEFAULTS).status_code == 200
    monkeypatch.setattr('utils.access_control.is_internal_request', lambda: False)
    assert admin_client.put('/api/notification-policy', json=policy.DEFAULTS).status_code == 403


def test_contract_expiry_event_and_cursor_are_idempotent(app):
    from datetime import date
    from utils.notifications import notify_contract_expiring
    with app.app_context():
        c = Customer(name='即将到期客户', contract_end_date=date.today())
        db.session.add(c); db.session.commit()
        notify_contract_expiring(); notify_contract_expiring()
        assert c.contract_expiry_notified == date.today()
        assert Event.query.filter_by(event_type='contract_expiring', audience='inbox', customer_id=c.id).count() == 1


def test_periodic_overdue_task_with_date_fields(app):
    """回归：scheduled_end 是 db.Date，periodic 不得再调用 .date()（曾致消费者每 2 秒崩溃）。"""
    with app.app_context():
        op = User.query.filter_by(username='op').one()
        customer = Customer(name='日期字段客户'); db.session.add(customer); db.session.flush()
        task = InspectionTask(
            title='日期字段逾期巡检', task_type='计划', status=C.TASK_SCHEDULED,
            customer_id=customer.id, assigned_to_user_id=op.id,
            scheduled_start=date(2026, 9, 1), scheduled_end=date(2026, 9, 5),
            planned_end=date(2026, 9, 5),
        )
        db.session.add(task); db.session.commit()
        db.session.expire_all()  # 从 DB 重新加载，确保日期字段是 date 对象
        periodic(datetime(2026, 9, 12, 2))
        assert Event.query.filter_by(
            event_type='reminder_task', entity_type='task', entity_id=task.id).count() >= 1


def test_notify_overdue_tasks_with_date_planned_end(app):
    """回归：planned_end 是 db.Date，逾期提醒不得再调用 .date()。"""
    with app.app_context():
        from utils.notifications import notify_overdue_tasks
        op = User.query.filter_by(username='op').one()
        customer = Customer(name='逾期计划客户'); db.session.add(customer); db.session.flush()
        db.session.add(InspectionTask(
            title='逾期计划任务', task_type='计划', status=C.TASK_PENDING,
            customer_id=customer.id, assigned_to_user_id=op.id,
            planned_start=date(2026, 7, 1), planned_end=date(2026, 8, 1),
        ))
        db.session.commit()
        db.session.expire_all()
        assert notify_overdue_tasks() == 1


def test_daily_job_provides_app_context(app, monkeypatch):
    """回归：APScheduler 线程执行每日任务时必须自带应用上下文。"""
    from utils import scheduler
    calls = []

    def fake_job():
        from models import User
        calls.append(User.query.count())  # 无 app context 会抛 RuntimeError

    monkeypatch.setattr(scheduler, '_daily_job', fake_job)
    scheduler._run_daily_job(app)
    assert calls and calls[0] >= 1
