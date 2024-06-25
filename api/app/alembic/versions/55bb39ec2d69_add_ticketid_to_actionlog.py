"""add_ticketid_to_actionlog

Revision ID: 55bb39ec2d69
Revises: 8f65d4e8ed06
Create Date: 2024-06-24 02:46:28.205696

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '55bb39ec2d69'
down_revision = '8f65d4e8ed06'
branch_labels = None
depends_on = None

def _delete_actionlog() -> None:
    op.get_bind().exec_driver_sql(
        "DELETE FROM actionlog"
    )


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    _delete_actionlog()
    op.add_column('actionlog', sa.Column('ticket_id', sa.String(length=36), nullable=True))
    op.alter_column('actionlog', 'service_id',
               existing_type=sa.VARCHAR(length=36),
               nullable=True)
    op.create_index(op.f('ix_actionlog_ticket_id'), 'actionlog', ['ticket_id'], unique=False)
    op.drop_constraint('ix_actionlog_service_id', 'actionlog', type_='foreignkey')
    op.create_foreign_key('ix_actionlog_ticket_id', 'actionlog', 'ticket', ['ticket_id'], ['ticket_id'], ondelete='SET NULL')
    op.create_foreign_key('ix_actionlog_service_id', 'actionlog', 'service', ['service_id'], ['service_id'], ondelete='SET NULL')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('ix_actionlog_service_id', 'actionlog', type_='foreignkey')
    op.drop_constraint('ix_actionlog_ticket_id', 'actionlog', type_='foreignkey')
    op.create_foreign_key('ix_actionlog_service_id', 'actionlog', 'service', ['service_id'], ['service_id'], ondelete='CASCADE')
    op.drop_index(op.f('ix_actionlog_ticket_id'), table_name='actionlog')
    op.alter_column('actionlog', 'service_id',
               existing_type=sa.VARCHAR(length=36),
               nullable=False)
    op.drop_column('actionlog', 'ticket_id')
    # ### end Alembic commands ###
