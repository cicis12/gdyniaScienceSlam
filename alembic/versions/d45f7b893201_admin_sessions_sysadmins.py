"""Add sysadmins and revocable admin sessions."""
from alembic import op
import sqlalchemy as sa

revision = 'd45f7b893201'
down_revision = 'c92d03e54f21'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('admin_users', sa.Column('is_sysadmin', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('admin_sessions',
                    sa.Column('token_hash', sa.String(64), primary_key=True),
                    sa.Column('admin_id', sa.Integer(), sa.ForeignKey('admin_users.id', ondelete='CASCADE'), nullable=False),
                    sa.Column('password_fingerprint', sa.String(64), nullable=False),
                    sa.Column('expires_at', sa.DateTime(), nullable=False))
    op.create_index('ix_admin_sessions_admin_id', 'admin_sessions', ['admin_id'])
    op.create_index('ix_admin_sessions_expires_at', 'admin_sessions', ['expires_at'])


def downgrade():
    op.drop_table('admin_sessions')
    op.drop_column('admin_users', 'is_sysadmin')
