from datetime import date, datetime
from types import SimpleNamespace

from utils import constants as C
from utils.notification_content import compact_content
from utils.notification_content import inspection_fields, ticket_fields, ticket_subject
from utils.wecom_notify import inspection_review_notification_content, task_status_notification_content


def completed_task(status):
    return SimpleNamespace(status=status, customer_rel=SimpleNamespace(name='景德镇市水利局'),
        assignee_rel=SimpleNamespace(realname='邱斌'), scheduled_start=date(2026, 9, 7),
        scheduled_end=date(2026, 9, 11), actual_start=datetime(2026, 9, 8, 8, 30),
        actual_end=datetime(2026, 9, 8, 17, 30), actual_effort=None)


def test_review_and_return_use_frozen_execution_time():
    task = completed_task(C.TASK_REVIEWING)
    submitted = inspection_review_notification_content(task, '提交人')
    task.status = C.TASK_RETURNED
    returned = task_status_notification_content(task, C.TASK_REVIEWING, '审核人', '补充照片', '补充照片')
    for content in (submitted, returned):
        assert '计划时间：**2026-09-07 至 2026-09-11' in content
        assert '实施结束：**2026-09-08 17:30' in content
        assert '累计耗时：**7小时30分钟' in content
        assert '累计人天：**0.94 人天' in content
        assert '任务期限' not in content
    assert returned.count('补充照片') == 1
    assert '审核结果' not in returned


def test_missing_timestamps_do_not_invent_execution_time():
    task = completed_task(C.TASK_RETURNED)
    task.actual_end = None
    content = task_status_notification_content(task, C.TASK_REVIEWING)
    assert '累计耗时' not in content
    assert '累计人天' not in content


def test_body_does_not_repeat_subject_or_identical_lines():
    assert compact_content('第三季度巡检', '第三季度巡检\n通知事项：审核通过\n通知事项：审核通过\n实施结束：10:00') == '通知事项：审核通过\n实施结束：10:00'


def test_global_channel_keeps_review_approval():
    content = task_status_notification_content(completed_task(C.TASK_DONE), C.TASK_REVIEWING)
    assert '通知事项：**巡检审核通过' in content
    assert '累计人天：**0.94 人天' in content


def test_inspection_completed_field_order_and_start_hides_final_metrics():
    task = completed_task(C.TASK_DONE)
    assert inspection_fields(task) == [
        ('计划时间', '2026-09-07 至 2026-09-11'),
        ('巡检地点', '景德镇市水利局'), ('巡检工程师', '邱斌'),
        ('任务状态', '已完成'), ('实施开始', '2026-09-08 08:30'),
        ('实施结束', '2026-09-08 17:30'), ('累计耗时', '7小时30分钟'),
        ('累计人天', '0.94 人天'),
    ]
    task.status = C.TASK_RUNNING
    assert [label for label, _ in inspection_fields(task)] == [
        '计划时间', '巡检地点', '巡检工程师', '任务状态', '实施开始',
    ]


def test_fault_subject_and_state_specific_fields(monkeypatch):
    from unittest.mock import Mock
    timing = Mock(return_value={'started_at': '2026-09-08 08:30',
        'finished_at': '2026-09-08 17:30', 'handling_duration_text': '7小时30分钟',
        'handling_person_days': 0.9375})
    monkeypatch.setattr('services.ticket_timing_service.ticket_timing_payload', timing)
    ticket = SimpleNamespace(customer_rel=SimpleNamespace(name='景德镇市水利局'),
        title='交换机故障', status=C.TICKET_PROCESSING, fault_location='',
        assigned_to='邱斌', visit_at=datetime(2026, 9, 7, 0, 30),
        started_at=datetime(2026, 9, 8, 0, 30))
    assert ticket_subject(ticket) == '景德镇市水利局交换机故障处置'
    ticket.title = ticket_subject(ticket)
    assert ticket_subject(ticket) == ticket.title
    assert ticket_fields(ticket) == [
        ('计划时间', '2026-09-07 08:30'), ('故障地点', '景德镇市水利局'),
        ('处置工程师', '邱斌'), ('任务状态', '处理中'), ('处置开始', '2026-09-08 08:30'),
    ]
    timing.assert_not_called()
    ticket.status = C.TICKET_CHECKED
    assert ticket_fields(ticket)[3:] == [
        ('任务状态', '已完成'), ('处置开始', '2026-09-08 08:30'),
        ('处置结束', '2026-09-08 17:30'), ('累计耗时', '7小时30分钟'),
        ('累计人天', '0.94 人天'),
    ]
