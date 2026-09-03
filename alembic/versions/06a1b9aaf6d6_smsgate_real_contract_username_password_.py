"""smsgate real contract: username, password, device_id

Revision ID: 06a1b9aaf6d6
Revises: ca6f50b72696
Create Date: 2026-09-03 09:24:40.287388

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06a1b9aaf6d6'
down_revision: Union[str, None] = 'ca6f50b72696'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Renamed (not dropped) so any already-configured tenant's encrypted
    # secret survives — the SMSGate API turned out to use HTTP Basic
    # (username/password) against a specific device, not an API key/sender
    # id. sms_api_key_encrypted -> sms_password_encrypted (same "encrypted
    # secret" semantics), sms_sender_id -> sms_device_id (same "plain
    # identifier" semantics, now interpreted as SMSGate's device_id).
    op.alter_column('organizations', 'sms_api_key_encrypted', new_column_name='sms_password_encrypted')
    op.alter_column('organizations', 'sms_sender_id', new_column_name='sms_device_id', type_=sa.String(length=100))
    op.add_column('organizations', sa.Column('sms_username', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'sms_username')
    op.alter_column('organizations', 'sms_device_id', new_column_name='sms_sender_id', type_=sa.String(length=50))
    op.alter_column('organizations', 'sms_password_encrypted', new_column_name='sms_api_key_encrypted')
