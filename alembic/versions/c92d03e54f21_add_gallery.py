"""Make the existing archive gallery editable."""
from alembic import op
import sqlalchemy as sa

revision = 'c92d03e54f21'
down_revision = 'b81c92d43e10'
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        'gallery_photos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('caption', sa.String(300), nullable=False),
        sa.Column('photo', sa.String(500), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
    )
    op.bulk_insert(table, [
        {'year': 2025, 'caption': 'Gdynia Science Slam 2025',
         'photo': f'/static/assets/images/gallery{number}.webp', 'sort_order': index}
        for index, number in enumerate([*range(2, 33), 34])
    ] + [{'year': 2024, 'caption': 'Gdynia Science Slam 2024',
          'photo': '/static/assets/images/gallery1.webp', 'sort_order': 0}])


def downgrade():
    op.drop_table('gallery_photos')
