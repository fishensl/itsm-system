# -*- coding: utf-8 -*-
"""敏感凭据传输信封的一次性 challenge。"""
from datetime import datetime

from models.base import db


class CredentialEnvelopeChallenge(db.Model):
    __tablename__ = 'credential_envelope_challenges'
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('issued','used','rejected','expired')",
            name='ck_credential_envelope_challenge_status'),
        db.CheckConstraint(
            'expires_at > created_at',
            name='ck_credential_envelope_challenge_expiry'),
        db.Index('ix_credential_challenge_user_status_expiry',
                 'user_id', 'status', 'expires_at'),
    )

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    username_snapshot = db.Column(db.String(64), nullable=False, default='')
    auth_version = db.Column(db.Integer, nullable=False, default=0)
    auth_strength = db.Column(db.String(32), nullable=False, default='')
    login_at = db.Column(db.DateTime, nullable=False)
    mfa_verified_at = db.Column(db.DateTime, nullable=False)
    session_binding_hash = db.Column(db.String(64), nullable=False, index=True)
    operation_binding_hash = db.Column(db.String(64), nullable=True)
    purpose = db.Column(db.String(64), nullable=False, index=True)
    method = db.Column(db.String(8), nullable=False)
    path = db.Column(db.String(256), nullable=False)
    target_type = db.Column(db.String(32), nullable=True)
    target_id = db.Column(db.String(64), nullable=True)
    history_id = db.Column(db.String(64), nullable=True)
    client_public_jwk = db.Column(db.Text, nullable=False)
    server_public_jwk = db.Column(db.Text, nullable=False)
    server_private_key_wrapped = db.Column(db.Text, nullable=True)
    wrap_kid = db.Column(db.String(64), nullable=False)
    salt = db.Column(db.String(64), nullable=False)
    context_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(16), nullable=False, default='issued', index=True)
    client_ciphertext_hash = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True)

    user_rel = db.relationship('User', backref='credential_envelope_challenges')


class CredentialDownloadTicket(db.Model):
    """敏感导出包授权后签发的短时、一次性下载票据。"""
    __tablename__ = 'credential_download_tickets'
    __table_args__ = (
        db.CheckConstraint(
            'expires_at > created_at',
            name='ck_credential_download_ticket_expiry'),
    )
    id = db.Column(db.String(64), primary_key=True)
    export_file_id = db.Column(
        db.Integer, db.ForeignKey('export_files.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    purpose = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True)

    export_file_rel = db.relationship('ExportFile', backref='credential_download_tickets')
    user_rel = db.relationship('User', backref='credential_download_tickets')
