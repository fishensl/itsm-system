"""Explicit one-time system bootstrap commands."""
import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import inspect

from models import User, db
from utils.crypto import initialize_master_key, master_key_status
from utils.password_policy import password_policy_error


def register_bootstrap_cli(app):
    @app.cli.command('init-admin')
    @click.option('--username', default='admin', show_default=True)
    @click.option('--realname', default='系统管理员', show_default=True)
    @click.password_option(confirmation_prompt=True)
    @with_appcontext
    def init_admin(username, realname, password):
        """Create the first administrator and, if missing, the first master key."""
        if 'users' not in inspect(db.engine).get_table_names():
            raise click.ClickException('数据库尚未迁移；请先运行 flask db upgrade')
        if User.query.count() != 0:
            raise click.ClickException('仅允许在空用户库执行 init-admin')
        error = password_policy_error(password)
        if error:
            raise click.ClickException(error)

        if master_key_status() == 'missing':
            initialize_master_key()
        user = User.create_with_password(
            username=(username or '').strip(),
            password=password,
            realname=(realname or '').strip(),
            role='admin',
        )
        user.must_change_password = True
        db.session.add(user)
        db.session.commit()
        current_app.logger.info('首次管理员已通过显式命令创建: %s', user.username)
        click.echo(f'管理员 {user.username} 已创建；首次登录必须修改密码。')
