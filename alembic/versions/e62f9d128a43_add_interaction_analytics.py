"""Add first-party link interaction analytics (disabled by default)."""
from alembic import op
import sqlalchemy as sa

revision = 'e62f9d128a43'
down_revision = 'd45f7b893201'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('interaction_links',
                    sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('label', sa.String(120), nullable=False),
                    sa.Column('path', sa.String(200), nullable=False),
                    sa.Column('active', sa.Boolean(), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_table('interaction_visits',
                    sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('link_id', sa.String(36), sa.ForeignKey('interaction_links.id', ondelete='CASCADE'), nullable=False),
                    sa.Column('path', sa.String(200), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), nullable=False))
    op.create_index('ix_interaction_visits_link_id', 'interaction_visits', ['link_id'])
    op.create_index('ix_interaction_visits_created_at', 'interaction_visits', ['created_at'])
    op.create_table('interaction_sections',
                    sa.Column('visit_id', sa.String(36), sa.ForeignKey('interaction_visits.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('section_id', sa.String(100), primary_key=True),
                    sa.Column('visible_ms', sa.Integer(), nullable=False),
                    sa.Column('clicks', sa.Integer(), nullable=False),
                    sa.Column('faq_opens', sa.Integer(), nullable=False))


def downgrade():
    op.drop_table('interaction_sections')
    op.drop_table('interaction_visits')
    op.drop_table('interaction_links')
