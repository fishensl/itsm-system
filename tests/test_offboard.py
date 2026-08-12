"""Offboarding revokes identity but preserves historical records."""


def test_offboard_preserves_user_and_business_history(admin_client, app):
    from models import Ticket, User, db
    with app.app_context():
        user = User.query.filter_by(username='op').first()
        user.vpn_account = 'vpn-op'
        user.mfa_enabled = True
        user.mfa_secret_encrypted = 'encrypted'
        ticket = Ticket(number='WO-OFFBOARD', title='离职历史记录', created_by='op')
        db.session.add(ticket)
        db.session.commit()
        user_id, ticket_id = user.id, ticket.id
        before = user.auth_version or 0

    response = admin_client.post(f'/api/users/{user_id}/offboard')
    assert response.status_code == 200
    with app.app_context():
        user = User.query.get(user_id)
        assert user is not None
        assert user.is_active is False
        assert user.auth_version == before + 1
        assert user.mfa_secret_encrypted is None
        assert Ticket.query.get(ticket_id) is not None


def test_offboard_self_is_rejected(admin_client, app):
    from models import User
    with app.app_context():
        admin_id = User.query.filter_by(username='admin').first().id
    response = admin_client.post(f'/api/users/{admin_id}/offboard')
    assert response.status_code == 400
