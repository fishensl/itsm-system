# -*- coding: utf-8 -*-
"""审核超时提醒：notify_review_timeout 对超时未审版本通知部门主管+admin"""
from datetime import datetime, timedelta

from models import db, User, Department, SubmissionVersion, Notification


def _setup(app, days_old, review_status='待审核'):
    """构造一条超时/未超时的提交版本；返回 entity_key"""
    with app.app_context():
        # 部门 + 主管 + 提交人（同一部门）
        dept = Department(name='测试部')
        db.session.add(dept)
        db.session.flush()
        head = User.create_with_password(username='head1', password='x',
                                         role='operator', realname='部门主管', department_id=dept.id)
        submitter = User.create_with_password(username='sub1', password='x',
                                              role='operator', realname='提交人', department_id=dept.id)
        db.session.add_all([head, submitter])
        db.session.flush()
        dept.head_id = head.id  # 部门主管指向 head
        db.session.commit()
        v = SubmissionVersion(
            entity_type='inspection', entity_id=999, version_no=1,
            review_status=review_status,
            submitted_by=submitter.id,
            created_at=datetime.utcnow() - timedelta(days=days_old),
            content_json='{}',
        )
        db.session.add(v)
        db.session.commit()
        return dept.id, head.id, submitter.id


class TestReviewTimeout:
    def test_timeout_notifies_head_and_admin(self, app):
        from utils.notifications import notify_review_timeout
        _, head_id, submitter_id = _setup(app, days_old=5)
        with app.app_context():
            sent = notify_review_timeout()
        assert sent == 1
        with app.app_context():
            # 主管收到通知
            n = Notification.query.filter_by(user_id=head_id).first()
            assert n is not None
            assert '审核超时' in n.title
            # 提交人自己不收（except_user_id）
            assert Notification.query.filter_by(user_id=submitter_id).count() == 0

    def test_fresh_review_no_notify(self, app):
        from utils.notifications import notify_review_timeout
        _setup(app, days_old=1)  # 未超时
        with app.app_context():
            assert notify_review_timeout() == 0

    def test_reviewed_no_notify(self, app):
        from utils.notifications import notify_review_timeout
        _setup(app, days_old=5, review_status='已通过')  # 已审
        with app.app_context():
            assert notify_review_timeout() == 0
