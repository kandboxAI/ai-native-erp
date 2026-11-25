"""Add the public tenant plugin activation ledger.

This migration only creates the ledger. Existing tenants must be verified and
backfilled by the tenant bootstrap command before their plugins become active.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_auth_tenant_plugin"
down_revision = "0002_public_vector_extension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_tenant_plugin",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False, comment="主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底"),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, comment="所属租户；引用 public.auth_tenant.id"),
        sa.Column("plugin_key", sa.String(length=64), nullable=False, comment="能力包稳定标识；与 plugin.toml 的 key 一致"),
        sa.Column("installed_version", sa.String(length=32), nullable=True, comment="最近一次成功开通的能力包版本；实际数据库修订以租户 alembic_version 为准"),
        sa.Column("provisioning_status_code", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False, comment="开通状态；字典 auth_tenant_plugin_provisioning_status"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False, comment="是否启用；仅 ready 且启用时开放入口"),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True, comment="最近一次启用时间"),
        sa.Column("last_error_type", sa.String(length=64), nullable=True, comment="最近开通失败的异常类别；不包含连接串、凭据或个人信息"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("created_by", sa.Uuid(), nullable=True, comment="创建人；引用登录账号；系统开通时为空"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="修改时间"),
        sa.Column("updated_by", sa.Uuid(), nullable=True, comment="修改人；引用登录账号；系统开通时为空"),
        sa.Column("flex_form", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False, comment="租户能力包扩展配置；默认 {}"),
        sa.ForeignKeyConstraint(["tenant_id"], ["public.auth_tenant.id"], name="fk_auth_tenant_plugin_tenant_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["public.auth_user.id"], name="fk_auth_tenant_plugin_created_by"),
        sa.ForeignKeyConstraint(["updated_by"], ["public.auth_user.id"], name="fk_auth_tenant_plugin_updated_by"),
        sa.PrimaryKeyConstraint("id", name="pk_auth_tenant_plugin"),
        schema="public",
        comment="租户启用的能力包：一行为某个租户对某个能力包的启用状态",
    )
    op.create_index("uk_auth_tenant_plugin_tenant_id_plugin_key", "auth_tenant_plugin", ["tenant_id", "plugin_key"], unique=True, schema="public")


def downgrade() -> None:
    op.drop_index("uk_auth_tenant_plugin_tenant_id_plugin_key", table_name="auth_tenant_plugin", schema="public")
    op.drop_table("auth_tenant_plugin", schema="public")
