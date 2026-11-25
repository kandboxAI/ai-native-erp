"""Independent L1 baseline for new core-only schemas. Legacy migrations are unchanged."""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from app.framework.db.types import PublicVector
from sqlalchemy.dialects import postgresql

revision = "core_0001"
down_revision = None
branch_labels = ("core",)
depends_on = None


def upgrade():
    # Tables first, then foreign keys, to support audit reference cycles.
    op.create_table('ai_resource_active',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('namespace', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='服务端定义的资源目录命名空间；租户内唯一'),
    sa.Column('bundle_id', sa.Uuid(), nullable=False, comment='活动索引版本；引用 ai_resource_bundle.id，发布事务内原子切换'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；维护脚本执行时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_resource_active')),
    sa.UniqueConstraint('namespace', name='uk_ai_resource_active_namespace'),
    comment='AI 资源活动索引：一行为当前租户一个目录命名空间的活动版本指针；发布事务原子切换'
    )
    op.create_table('ai_resource_bundle',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('namespace', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='服务端定义的资源目录命名空间'),
    sa.Column('revision', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='目录与向量模型身份的 SHA256 版本摘要'),
    sa.Column('model', sa.Text(), nullable=False, comment='向量模型身份；包含接口、模型、维度和文本版本，不含密钥'),
    sa.Column('dimensions', sa.Integer(), nullable=False, comment='向量维度；正整数'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；维护脚本执行时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.CheckConstraint('dimensions > 0', name=op.f('ck_ai_resource_bundle_dimensions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_resource_bundle')),
    sa.UniqueConstraint('namespace', 'revision', name='uk_ai_resource_bundle_namespace_revision'),
    comment='AI 资源索引版本：一行为当前租户一个命名空间的一次元数据索引发布；不包含业务记录'
    )
    op.create_table('ai_resource_document',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('bundle_id', sa.Uuid(), nullable=False, comment='所属索引版本；引用 ai_resource_bundle.id，命名空间和版本摘要由该版本取得'),
    sa.Column('document_key', sa.Text(), nullable=False, comment='索引定义标识；资源、接口或指标的稳定标识，不是业务记录编号'),
    sa.Column('content_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='审核定义的 SHA256 摘要；检索时与当前授权定义核对'),
    sa.Column('embedding', PublicVector(), nullable=False, comment='审核元数据的稠密向量；维度由所属索引版本记录'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；维护脚本执行时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_resource_document')),
    sa.UniqueConstraint('bundle_id', 'document_key', name='uk_ai_resource_document_bundle_id_document_key'),
    comment='AI 资源索引定义：一行为一个版本内的已审核表、接口或指标定义的向量；不包含业务记录'
    )
    op.create_table('audit_operation_log',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('module_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='模块；字典 sys_module'),
    sa.Column('action_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='操作类型；字典 audit_action'),
    sa.Column('target_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='操作对象类型；字典 audit_target_type'),
    sa.Column('target_id', sa.Uuid(), nullable=True, comment='操作对象；多态引用'),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True, comment='操作人'),
    sa.Column('is_agent_action', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否智能体代为操作'),
    sa.Column('content', sa.Text(), nullable=True, comment='操作摘要'),
    sa.Column('ip_address', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='IP 地址；敏感：个人'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_operation_log')),
    comment='操作日志：一行为一次写操作（含智能体代为操作）。只追加，不可修改、删除。'
    )
    op.create_table('file_attachment',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('uploader_user_id', sa.Uuid(), nullable=False, comment='上传人；不对外返回'),
    sa.Column('storage_backend', sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False, comment='存储后端：oss 或 local（仅开发环境）'),
    sa.Column('storage_key', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False, comment='对象键：<租户 schema>/<场景>/<年>/<月>/<id>.<扩展名>'),
    sa.Column('original_file_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False, comment='原始文件名'),
    sa.Column('extension', sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False, comment='扩展名'),
    sa.Column('content_type', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='内容类型'),
    sa.Column('file_kind_code', sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False, comment='文件类别；字典 file_kind'),
    sa.Column('file_size', sa.BigInteger(), nullable=False, comment='文件大小（字节）；申请上传时声明，完成上传时按存储中的实际大小核对'),
    sa.Column('content_md5', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False, comment='内容 MD5（Base64）；客户端上传时带 Content-MD5，由存储校验完整性'),
    sa.Column('width', sa.Integer(), nullable=True, comment='图片宽度；图片时填写'),
    sa.Column('height', sa.Integer(), nullable=True, comment='图片高度；图片时填写'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=16), server_default=sa.text("'uploading'"), nullable=False, comment='状态；字典 file_attachment_status'),
    sa.Column('scene_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='上传场景；决定允许的类型、大小与数量，由业务模块登记'),
    sa.Column('business_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='业务类型；取业务主表的表名，如 fac_patrol_record'),
    sa.Column('business_id', sa.Uuid(), nullable=True, comment='业务单据；多态引用，由业务类型决定所指的表'),
    sa.Column('business_sub_id', sa.Uuid(), nullable=True, comment='业务子单据；如报修的某条进度'),
    sa.Column('sort_no', sa.Integer(), server_default=sa.text('0'), nullable=False, comment='排序'),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, comment='过期时间；uploading、pending 超时后由清理任务删除记录和对象'),
    sa.Column('bound_at', sa.DateTime(timezone=True), nullable=True, comment='绑定时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='上传人'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_file_attachment')),
    comment='文件与附件：一行为一个上传的文件。uploading 表示等待客户端直传，pending 表示已上传、待业务绑定，bound 表示已绑定且不可复用。任何接口都不返回上传人。'
    )
    op.create_table('int_outbox_event',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('producer_module_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='生产模块；字典 sys_module'),
    sa.Column('event_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='事件类型；字典 int_event_type'),
    sa.Column('exchange', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='交换机'),
    sa.Column('routing_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='路由键'),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='事件内容'),
    sa.Column('header_meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='报文头'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='状态；字典 int_outbox_status'),
    sa.Column('retry_count', sa.Integer(), server_default=sa.text('0'), nullable=False, comment='已重试次数'),
    sa.Column('max_retries', sa.Integer(), nullable=False, comment='最多重试次数'),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True, comment='下次尝试时间'),
    sa.Column('last_error', sa.Text(), nullable=True, comment='最近错误'),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True, comment='发送时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_int_outbox_event')),
    comment='事件出站：一行为一个待发送或已发送的领域事件。事务内写入，再由后台投递；通知、待办、智能体触发都从这里获取事件。'
    )
    op.create_table('md_organization',
    sa.Column('party_id', sa.Uuid(), nullable=False, comment='主体 ID；主键兼外键，引用 md_party.id'),
    sa.Column('legal_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='法定名称'),
    sa.Column('credit_no', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='统一社会信用代码'),
    sa.Column('organization_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='机构类型；字典 md_organization_type'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('party_id', name=op.f('pk_md_organization')),
    comment='外部机构：一行为一个与业务往来的外部机构。生源学校、实习企业、供应商等外部机构；不是本租户的组织架构（那是 `sys_org`）。子类型表，主键为 `party_id`。'
    )
    op.create_table('md_party',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('party_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='主体类型；字典 md_party_type'),
    sa.Column('display_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='显示名称'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否有效'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_md_party')),
    comment='主体：一行为一个参与业务的主体（自然人或机构）。人员和外部机构的共同父表。'
    )
    op.create_table('md_person',
    sa.Column('party_id', sa.Uuid(), nullable=False, comment='主体 ID；主键兼外键，引用 md_party.id'),
    sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='姓名；敏感：个人'),
    sa.Column('gender_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='性别；字典 md_gender'),
    sa.Column('birth_date', sa.Date(), nullable=True, comment='出生日期；敏感：个人'),
    sa.Column('user_id', sa.Uuid(), nullable=True, comment='租户内用户；有账号的人才有；本租户内唯一'),
    sa.Column('photo_file_id', sa.Uuid(), nullable=True, comment='照片文件；敏感：个人；引用 file_attachment'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('party_id', name=op.f('pk_md_person')),
    comment='人员：一行为一个人（终身一条）。子类型表，主键为 `party_id`。学生、教师、监护人都通过 `party_id` 关联到这里。'
    )
    op.create_table('md_person_contact',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('party_id', sa.Uuid(), nullable=False, comment='人员'),
    sa.Column('contact_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='联系方式类型；字典 md_contact_type'),
    sa.Column('contact_value', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False, comment='联系方式；敏感：个人'),
    sa.Column('contact_value_hash', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='联系方式哈希；按手机号查人用'),
    sa.Column('purpose_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='用途；字典 md_contact_purpose'),
    sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否主要联系方式'),
    sa.Column('is_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否已验证'),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True, comment='验证时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_md_person_contact')),
    comment='人员联系方式：一行为一个人的一个联系方式。一人可有多个手机号、住址等；登录手机号在 `public.auth_user`，与这里含义不同。'
    )
    op.create_table('md_person_pii',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('party_id', sa.Uuid(), nullable=False, comment='人员'),
    sa.Column('identity_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='证件类型；字典 md_identity_type'),
    sa.Column('identity_no_encrypted', sa.Text(), nullable=False, comment='证件号（密文）；敏感：机密'),
    sa.Column('identity_no_hash', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='证件号哈希；敏感：机密；用于精确查找与去重'),
    sa.Column('identity_no_masked', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='证件号（脱敏）；敏感：机密；如 3501**********1234'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_md_person_pii')),
    comment='人员身份信息：一行为一个人的一种证件（personal identity information）。人员身份信息（personal identity information）：证件类机密信息，单独授权，加密存储。AI 和报表不可读取。'
    )
    op.create_table('ntf_channel_binding',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('user_id', sa.Uuid(), nullable=False, comment='用户'),
    sa.Column('channel_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='渠道；字典 ntf_channel'),
    sa.Column('provider_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='服务商；字典 ntf_provider'),
    sa.Column('appid', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='应用 ID'),
    sa.Column('external_user_no', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='外部用户标识；敏感：个人；如 openid'),
    sa.Column('unionid', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='unionid；敏感：个人'),
    sa.Column('bound_at', sa.DateTime(timezone=True), nullable=True, comment='绑定时间'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否有效'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_channel_binding')),
    comment='通知渠道绑定：一行为一个用户在一个外部渠道的绑定。'
    )
    op.create_table('ntf_delivery_log',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('recipient_id', sa.Uuid(), nullable=False, comment='通知接收人'),
    sa.Column('channel_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='渠道；字典 ntf_channel'),
    sa.Column('provider_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='服务商；字典 ntf_provider'),
    sa.Column('target_address', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True, comment='投递地址；敏感：个人；openid 或手机号'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='投递状态；字典 ntf_delivery_status'),
    sa.Column('request_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='请求报文'),
    sa.Column('response_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='响应报文'),
    sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_delivery_log')),
    comment='通知投递日志：一行为一次渠道投递尝试。'
    )
    op.create_table('ntf_event_log',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('scene_id', sa.Uuid(), nullable=True, comment='通知场景'),
    sa.Column('business_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='业务类型；字典 wf_business_type'),
    sa.Column('business_id', sa.Uuid(), nullable=True, comment='业务单据；多态引用'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='处理结果；字典 ntf_event_status'),
    sa.Column('message', sa.Text(), nullable=True, comment='说明'),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='事件内容'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_event_log')),
    comment='通知事件日志：一行为一次业务事件的处理记录。'
    )
    op.create_table('ntf_notice',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=256), nullable=False, comment='标题'),
    sa.Column('summary', sa.Text(), nullable=True, comment='内容'),
    sa.Column('notice_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='公告类型；字典 ntf_notice_type'),
    sa.Column('is_shown_on_home', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否在首页显示'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='状态；字典 ntf_notice_status'),
    sa.Column('published_by', sa.Uuid(), nullable=True, comment='发布人'),
    sa.Column('publisher_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='发布人姓名；快照'),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True, comment='发布时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_notice')),
    comment='公告：一行为一条通知公告。'
    )
    op.create_table('ntf_notice_read',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('notice_id', sa.Uuid(), nullable=False, comment='公告'),
    sa.Column('user_id', sa.Uuid(), nullable=False, comment='用户'),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=False, comment='阅读时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_notice_read')),
    comment='公告阅读记录：一行为一个用户阅读一条公告。'
    )
    op.create_table('ntf_notice_target',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('notice_id', sa.Uuid(), nullable=False, comment='公告'),
    sa.Column('target_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='对象类型；字典 ntf_target_type'),
    sa.Column('role_id', sa.Uuid(), nullable=True, comment='角色'),
    sa.Column('user_id', sa.Uuid(), nullable=True, comment='用户'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_notice_target')),
    comment='公告接收范围：一行为一条公告的一个接收对象。'
    )
    op.create_table('ntf_notification',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('scene_id', sa.Uuid(), nullable=False, comment='通知场景'),
    sa.Column('scene_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='场景名称；快照'),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=256), nullable=False, comment='标题'),
    sa.Column('content', sa.Text(), nullable=True, comment='内容'),
    sa.Column('severity_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='重要程度；字典 ntf_severity'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='状态；字典 ntf_notification_status'),
    sa.Column('source_module_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='来源模块；字典 sys_module'),
    sa.Column('business_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='业务类型；字典 wf_business_type'),
    sa.Column('business_id', sa.Uuid(), nullable=True, comment='业务单据；多态引用'),
    sa.Column('event_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='事件幂等键'),
    sa.Column('redirect_url', sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=True, comment='跳转地址'),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='附加信息'),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, comment='发生时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_notification')),
    comment='站内通知：一行为一次业务事件产生的一条通知。'
    )
    op.create_table('ntf_preference',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('user_id', sa.Uuid(), nullable=False, comment='用户'),
    sa.Column('scene_id', sa.Uuid(), nullable=False, comment='通知场景'),
    sa.Column('channel_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='渠道；字典 ntf_channel'),
    sa.Column('is_enabled_by_user', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否接收'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_preference')),
    comment='通知偏好：一行为一个用户对一个场景一个渠道的偏好。'
    )
    op.create_table('ntf_recipient',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('notification_id', sa.Uuid(), nullable=False, comment='通知'),
    sa.Column('user_id', sa.Uuid(), nullable=False, comment='接收人'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='阅读状态；字典 ntf_recipient_status'),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True, comment='阅读时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_recipient')),
    comment='通知接收人：一行为一条通知的一个接收人。'
    )
    op.create_table('ntf_route',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('scene_id', sa.Uuid(), nullable=False, comment='通知场景'),
    sa.Column('target_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='接收对象类型；字典 ntf_target_type'),
    sa.Column('role_id', sa.Uuid(), nullable=True, comment='角色'),
    sa.Column('user_id', sa.Uuid(), nullable=True, comment='用户'),
    sa.Column('permission_id', sa.Uuid(), nullable=True, comment='权限'),
    sa.Column('actor_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='业务相关人标识；如 applicant、homeroom_teacher'),
    sa.Column('org_scope_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='组织范围；字典 ntf_route_org_scope'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_route')),
    comment='通知路由：一行为一个场景的一条接收人规则。'
    )
    op.create_table('ntf_scene',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('scene_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='场景标识'),
    sa.Column('scene_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='场景名称'),
    sa.Column('module_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='所属模块；字典 sys_module'),
    sa.Column('description', sa.Text(), nullable=True, comment='说明'),
    sa.Column('severity_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='重要程度；字典 ntf_severity'),
    sa.Column('fallback_policy_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='渠道降级策略；字典 ntf_fallback_policy'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_scene')),
    comment='通知场景：一行为一个由业务代码触发的通知场景。`scene_key` 由代码定义，如 leave_approved。'
    )
    op.create_table('ntf_scene_channel',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('scene_id', sa.Uuid(), nullable=False, comment='通知场景'),
    sa.Column('channel_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='渠道；字典 ntf_channel'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_scene_channel')),
    comment='场景渠道：一行为一个通知场景启用的一个渠道。'
    )
    op.create_table('ntf_template',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('scene_id', sa.Uuid(), nullable=False, comment='通知场景'),
    sa.Column('channel_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='渠道；字典 ntf_channel'),
    sa.Column('title_template', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True, comment='标题模板'),
    sa.Column('content_template', sa.Text(), nullable=True, comment='内容模板'),
    sa.Column('wechat_template_no', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='微信模板标识'),
    sa.Column('data_mapping_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='字段映射配置'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ntf_template')),
    comment='通知模板：一行为一个场景在一个渠道上的模板。'
    )
    op.create_table('sys_department',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('department_no', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='部门编号'),
    sa.Column('department_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='部门名称'),
    sa.Column('parent_id', sa.Uuid(), nullable=True, comment='上级部门'),
    sa.Column('manager_user_id', sa.Uuid(), nullable=True, comment='部门负责人'),
    sa.Column('supervisor_party_id', sa.Uuid(), nullable=True, comment='分管领导；全系统唯一的分管领导来源'),
    sa.Column('sort_no', sa.Integer(), nullable=True, comment='排序'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_department')),
    comment='部门：一行为一个部门（如教务科、学生科、教研组）。部门树；负责人引用租户内用户。'
    )
    op.create_table('sys_dict',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('dict_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='字典编码；如 edu_leave_type；字典表自身豁免“_code 引用字典”规则'),
    sa.Column('dict_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='字典名称'),
    sa.Column('description', sa.Text(), nullable=True, comment='说明'),
    sa.Column('is_tenant_extensible', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='学校可否扩展；是否允许学校增加自己的字典项'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_dict')),
    comment='字典：一行为一个字典（如“请假类型”）。每个租户 schema 一份完整字典。内置字典由平台定义，开通租户时生成、升级时同步。'
    )
    op.create_table('sys_dict_item',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('dict_id', sa.Uuid(), nullable=False, comment='所属字典'),
    sa.Column('item_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='取值编码；小写英文，业务表中保存的值'),
    sa.Column('item_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='取值名称；界面显示的中文'),
    sa.Column('sort_no', sa.Integer(), nullable=True, comment='排序'),
    sa.Column('is_builtin', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否内置；平台定义的内置项不可删除，只能停用'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_dict_item')),
    comment='字典项：一行为字典中的一个取值。业务表 `_code` 字段存的就是 `item_code`。内置项由平台定义，学校自己增加的项 `is_builtin` 为否。'
    )
    op.create_table('sys_job',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('job_no', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='职务编号'),
    sa.Column('job_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='职务名称'),
    sa.Column('job_family_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='职务序列；字典 sys_job_family'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_job')),
    comment='职务：一行为一类工作（如语文教师、护理员、财务会计）。不属于任何部门。'
    )
    op.create_table('sys_menu',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('menu_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='菜单标识'),
    sa.Column('menu_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='菜单名称'),
    sa.Column('menu_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='菜单类型；字典 sys_menu_type'),
    sa.Column('parent_id', sa.Uuid(), nullable=True, comment='上级菜单'),
    sa.Column('path', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True, comment='路由路径'),
    sa.Column('component', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True, comment='页面组件'),
    sa.Column('icon', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='图标'),
    sa.Column('permission_id', sa.Uuid(), nullable=True, comment='所需权限'),
    sa.Column('is_external', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否外链'),
    sa.Column('external_url', sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=True, comment='外链地址'),
    sa.Column('open_target_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='打开方式；字典 sys_open_target'),
    sa.Column('sort_no', sa.Integer(), nullable=True, comment='排序'),
    sa.Column('is_visible', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否显示'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_menu')),
    comment='菜单：一行为管理端的一个菜单、目录或按钮。菜单每个租户一份，`menu_key` 对应前端页面组件。'
    )
    op.create_table('sys_miniapp_menu',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('portal_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='门户；字典 sys_miniapp_portal'),
    sa.Column('menu_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='菜单标识；门户内唯一'),
    sa.Column('menu_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='菜单名称'),
    sa.Column('group_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='分组标识'),
    sa.Column('group_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='分组名称'),
    sa.Column('path', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True, comment='页面路径'),
    sa.Column('sort_no', sa.Integer(), nullable=True, comment='排序'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_miniapp_menu')),
    comment='小程序菜单：一行为小程序某个门户中的一个菜单项。'
    )
    op.create_table('sys_org',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_no', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='组织编号'),
    sa.Column('org_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='组织名称'),
    sa.Column('org_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='组织类型；字典 sys_org_type'),
    sa.Column('parent_id', sa.Uuid(), nullable=True, comment='上级组织'),
    sa.Column('contact_name', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='联系人；敏感：个人'),
    sa.Column('contact_phone', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True, comment='联系电话；敏感：个人'),
    sa.Column('province', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='省'),
    sa.Column('city', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='市'),
    sa.Column('district', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='区县'),
    sa.Column('address', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True, comment='详细地址'),
    sa.Column('sort_no', sa.Integer(), nullable=True, comment='排序'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_org')),
    comment='组织：一行为组织树中的一个节点（集团、学校或校区）。本租户内部的组织架构。教学数据的 `org_id` 指向校区；只有一个校区的学校，校区即学校本身。'
    )
    op.create_table('sys_permission',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('permission_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='权限标识；如 leave:approve'),
    sa.Column('permission_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='权限名称'),
    sa.Column('module_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='所属模块；字典 sys_module'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_permission')),
    comment='权限：一行为一个功能权限点。权限由代码定义，开通租户时从模板生成；接口按 `permission_key` 校验。'
    )
    op.create_table('sys_position',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('position_no', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='岗位编号'),
    sa.Column('position_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='岗位名称'),
    sa.Column('department_id', sa.Uuid(), nullable=False, comment='所属部门'),
    sa.Column('job_id', sa.Uuid(), nullable=True, comment='职务'),
    sa.Column('parent_position_id', sa.Uuid(), nullable=True, comment='上级岗位；汇报线'),
    sa.Column('is_department_head', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否负责人岗位；在任者即部门负责人'),
    sa.Column('headcount', sa.Integer(), nullable=True, comment='编制人数；为空表示不限'),
    sa.Column('sort_no', sa.Integer(), nullable=True, comment='排序'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_position')),
    comment='岗位：一行为编制中的一个岗位。上级岗位构成汇报线（不能成环）；同一部门最多一个负责人岗位。'
    )
    op.create_table('sys_role',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('role_no', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='角色编号'),
    sa.Column('role_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='角色名称'),
    sa.Column('description', sa.Text(), nullable=True, comment='说明'),
    sa.Column('data_scope_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='数据范围；字典 sys_data_scope'),
    sa.Column('is_builtin', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否内置；内置角色不可删除'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_role')),
    comment='角色：一行为一个角色。角色是学校配置的权限与数据范围组合。代码不按角色名判断；内置管理员角色以 `is_builtin` 防止删除，数据范围为全部、拥有全部权限。'
    )
    op.create_table('sys_role_menu',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('role_id', sa.Uuid(), nullable=False, comment='角色'),
    sa.Column('menu_id', sa.Uuid(), nullable=False, comment='菜单'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_role_menu')),
    comment='角色菜单：一行为一个角色可见的一个菜单。'
    )
    op.create_table('sys_role_miniapp_menu',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('role_id', sa.Uuid(), nullable=False, comment='角色'),
    sa.Column('miniapp_menu_id', sa.Uuid(), nullable=False, comment='小程序菜单'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_role_miniapp_menu')),
    comment='角色小程序菜单：一行为一个角色在小程序中可见的一个菜单。'
    )
    op.create_table('sys_role_permission',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('role_id', sa.Uuid(), nullable=False, comment='角色'),
    sa.Column('permission_id', sa.Uuid(), nullable=False, comment='权限'),
    sa.Column('data_scope_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='数据范围；字典 sys_data_scope；为空时取角色的数据范围'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_role_permission')),
    comment='角色权限：一行为一个角色拥有的一个权限。'
    )
    op.create_table('sys_setting',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('setting_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='参数标识；代码中引用，如 password_min_length'),
    sa.Column('setting_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='参数名称'),
    sa.Column('setting_value', sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=True, comment='参数值'),
    sa.Column('value_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='值类型；字典 sys_value_type'),
    sa.Column('setting_group_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='参数分组；字典 sys_setting_group'),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True, comment='说明'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_setting')),
    comment='系统参数：一行为一个系统参数。代码读取的系统参数，`setting_key` 由代码定义，创建后不可修改。'
    )
    op.create_table('sys_user',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('auth_user_id', sa.Uuid(), nullable=False, comment='登录账号；跨 schema 引用 `public.auth_user`；本租户内唯一'),
    sa.Column('display_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='显示名称；敏感：个人'),
    sa.Column('avatar_url', sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=True, comment='头像'),
    sa.Column('department_id', sa.Uuid(), nullable=True, comment='所属部门'),
    sa.Column('org_access_mode_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='组织访问方式；字典 sys_org_access_mode'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_user')),
    comment='租户内用户：一行为一个登录账号在一个租户中的用户身份。用户进入租户后的身份：所属组织、部门、角色都挂在这里。姓名、电话等人员信息在 `md_person`（经 `md_person.user_id` 关联）。'
    )
    op.create_table('sys_user_org',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('user_id', sa.Uuid(), nullable=False, comment='用户'),
    sa.Column('access_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='授权类型；字典 sys_user_org_access_type'),
    sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否主组织'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_user_org')),
    comment='用户可访问的组织：一行为一个用户被授权访问的一个组织。用户除主组织外还能访问的组织（如集团管理人员访问多个校区）。'
    )
    op.create_table('sys_user_role',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('user_id', sa.Uuid(), nullable=False, comment='用户'),
    sa.Column('role_id', sa.Uuid(), nullable=False, comment='角色'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_user_role')),
    comment='用户角色：一行为一个用户拥有的一个角色。'
    )
    op.create_table('wf_cc_record',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('instance_id', sa.Uuid(), nullable=False, comment='流程实例'),
    sa.Column('task_id', sa.Uuid(), nullable=True, comment='审批任务'),
    sa.Column('task_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='节点标识'),
    sa.Column('business_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='业务类型；字典 wf_business_type'),
    sa.Column('business_id', sa.Uuid(), nullable=False, comment='业务单据；多态引用'),
    sa.Column('cc_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='抄送对象类型；字典 wf_cc_type'),
    sa.Column('recipient_user_id', sa.Uuid(), nullable=False, comment='接收人'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='阅读状态；字典 wf_read_status'),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True, comment='阅读时间'),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='附加信息'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wf_cc_record')),
    comment='抄送记录：一行为一次抄送给一个人。'
    )
    op.create_table('wf_definition',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('definition_no', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='流程编号'),
    sa.Column('definition_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='流程名称'),
    sa.Column('business_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='业务类型；字典 wf_business_type'),
    sa.Column('description', sa.Text(), nullable=True, comment='说明'),
    sa.Column('current_version_id', sa.Uuid(), nullable=True, comment='当前版本'),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='删除时间；软删除；有效数据为空'),
    sa.Column('deleted_by', sa.Uuid(), nullable=True, comment='删除人；与删除时间同时出现'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wf_definition')),
    comment='流程定义：一行为一个审批流程。'
    )
    op.create_table('wf_definition_version',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('definition_id', sa.Uuid(), nullable=False, comment='流程定义'),
    sa.Column('version_no', sa.Integer(), nullable=False, comment='版本号'),
    sa.Column('bpmn_process_no', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='BPMN 流程标识'),
    sa.Column('bpmn_xml', sa.Text(), nullable=True, comment='BPMN 定义'),
    sa.Column('spiff_spec_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='引擎规格快照；快照'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='状态；字典 wf_definition_version_status'),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True, comment='发布时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wf_definition_version')),
    comment='流程版本：一行为流程的一个版本。'
    )
    op.create_table('wf_instance',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('definition_id', sa.Uuid(), nullable=False, comment='流程定义'),
    sa.Column('version_id', sa.Uuid(), nullable=False, comment='流程版本'),
    sa.Column('business_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='业务类型；字典 wf_business_type'),
    sa.Column('business_id', sa.Uuid(), nullable=False, comment='业务单据；多态引用，类型见业务类型'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='状态；字典 wf_instance_status'),
    sa.Column('bpmn_activity_no', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True, comment='当前节点'),
    sa.Column('workflow_state_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='引擎状态；快照'),
    sa.Column('started_by', sa.Uuid(), nullable=False, comment='发起人'),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, comment='发起时间'),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True, comment='结束时间'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wf_instance')),
    comment='流程实例：一行为一次审批流程的运行。'
    )
    op.create_table('wf_task',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('instance_id', sa.Uuid(), nullable=False, comment='流程实例'),
    sa.Column('task_key', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='节点标识；BPMN 中的任务节点'),
    sa.Column('task_name', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False, comment='任务名称'),
    sa.Column('spiff_task_no', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='引擎任务标识'),
    sa.Column('assignee_type_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='审批人类型；字典 wf_assignee_type'),
    sa.Column('assignee_value', sqlmodel.sql.sqltypes.AutoString(length=256), nullable=True, comment='审批人配置'),
    sa.Column('approval_mode_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='多人审批方式；字典 wf_approval_mode'),
    sa.Column('assignee_user_id', sa.Uuid(), nullable=True, comment='处理人'),
    sa.Column('status_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='状态；字典 wf_task_status'),
    sa.Column('arrived_at', sa.DateTime(timezone=True), nullable=False, comment='到达时间'),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='完成时间'),
    sa.Column('completed_by', sa.Uuid(), nullable=True, comment='完成人'),
    sa.Column('outcome_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True, comment='审批结果；字典 wf_task_outcome'),
    sa.Column('comment', sa.Text(), nullable=True, comment='审批意见'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wf_task')),
    comment='审批任务：一行为流程中的一个待办审批任务。'
    )
    op.create_table('wf_task_action',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('instance_id', sa.Uuid(), nullable=False, comment='流程实例'),
    sa.Column('task_id', sa.Uuid(), nullable=True, comment='审批任务'),
    sa.Column('action_code', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False, comment='动作；字典 wf_action'),
    sa.Column('actor_user_id', sa.Uuid(), nullable=False, comment='操作人'),
    sa.Column('comment', sa.Text(), nullable=True, comment='意见'),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='附加信息'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wf_task_action')),
    comment='审批记录：一行为一次审批动作。'
    )
    op.create_table('wf_task_candidate',
    sa.Column('id', sa.Uuid(), server_default=sa.text('uuidv7()'), nullable=False, comment='主键；UUIDv7：应用生成，数据库默认值 uuidv7()（PostgreSQL 18 内置）兜底'),
    sa.Column('org_id', sa.Uuid(), nullable=False, comment='所属组织；学校或校区；数据范围按它过滤'),
    sa.Column('task_id', sa.Uuid(), nullable=False, comment='审批任务'),
    sa.Column('user_id', sa.Uuid(), nullable=False, comment='候选人'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
    sa.Column('created_by', sa.Uuid(), nullable=True, comment='创建人；系统任务创建时为空'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='修改时间'),
    sa.Column('updated_by', sa.Uuid(), nullable=True, comment='修改人'),
    sa.Column('flex_form', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='扩展字段；租户自定义字段，结构见动态表单定义；默认 {}'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wf_task_candidate')),
    comment='审批候选人：一行为一个审批任务的一个候选处理人。'
    )
    op.create_foreign_key(op.f('fk_ai_resource_active_bundle_id'), 'ai_resource_active', 'ai_resource_bundle', ['bundle_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key(op.f('fk_ai_resource_active_created_by'), 'ai_resource_active', 'sys_user', ['created_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_ai_resource_active_updated_by'), 'ai_resource_active', 'sys_user', ['updated_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_ai_resource_bundle_created_by'), 'ai_resource_bundle', 'sys_user', ['created_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_ai_resource_bundle_updated_by'), 'ai_resource_bundle', 'sys_user', ['updated_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_ai_resource_document_bundle_id'), 'ai_resource_document', 'ai_resource_bundle', ['bundle_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_ai_resource_document_created_by'), 'ai_resource_document', 'sys_user', ['created_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_ai_resource_document_updated_by'), 'ai_resource_document', 'sys_user', ['updated_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_audit_operation_log_actor_user_id'), 'audit_operation_log', 'sys_user', ['actor_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_audit_operation_log_created_by'), 'audit_operation_log', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_audit_operation_log_org_id'), 'audit_operation_log', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_file_attachment_created_by'), 'file_attachment', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_file_attachment_org_id'), 'file_attachment', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_file_attachment_updated_by'), 'file_attachment', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_file_attachment_uploader_user_id'), 'file_attachment', 'sys_user', ['uploader_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_int_outbox_event_created_by'), 'int_outbox_event', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_int_outbox_event_updated_by'), 'int_outbox_event', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_organization_created_by'), 'md_organization', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_organization_deleted_by'), 'md_organization', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_organization_party_id'), 'md_organization', 'md_party', ['party_id'], ['id'])
    op.create_foreign_key(op.f('fk_md_organization_updated_by'), 'md_organization', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_party_created_by'), 'md_party', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_party_deleted_by'), 'md_party', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_party_updated_by'), 'md_party', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_created_by'), 'md_person', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_deleted_by'), 'md_person', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_party_id'), 'md_person', 'md_party', ['party_id'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_photo_file_id'), 'md_person', 'file_attachment', ['photo_file_id'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_updated_by'), 'md_person', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_user_id'), 'md_person', 'sys_user', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_contact_created_by'), 'md_person_contact', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_contact_deleted_by'), 'md_person_contact', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_contact_party_id'), 'md_person_contact', 'md_person', ['party_id'], ['party_id'])
    op.create_foreign_key(op.f('fk_md_person_contact_updated_by'), 'md_person_contact', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_pii_created_by'), 'md_person_pii', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_pii_deleted_by'), 'md_person_pii', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_md_person_pii_party_id'), 'md_person_pii', 'md_person', ['party_id'], ['party_id'])
    op.create_foreign_key(op.f('fk_md_person_pii_updated_by'), 'md_person_pii', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_channel_binding_created_by'), 'ntf_channel_binding', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_channel_binding_deleted_by'), 'ntf_channel_binding', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_channel_binding_updated_by'), 'ntf_channel_binding', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_channel_binding_user_id'), 'ntf_channel_binding', 'sys_user', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_delivery_log_created_by'), 'ntf_delivery_log', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_delivery_log_org_id'), 'ntf_delivery_log', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_delivery_log_recipient_id'), 'ntf_delivery_log', 'ntf_recipient', ['recipient_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_event_log_created_by'), 'ntf_event_log', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_event_log_org_id'), 'ntf_event_log', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_event_log_scene_id'), 'ntf_event_log', 'ntf_scene', ['scene_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_created_by'), 'ntf_notice', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_deleted_by'), 'ntf_notice', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_org_id'), 'ntf_notice', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_published_by'), 'ntf_notice', 'sys_user', ['published_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_updated_by'), 'ntf_notice', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_read_created_by'), 'ntf_notice_read', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_read_notice_id'), 'ntf_notice_read', 'ntf_notice', ['notice_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_read_org_id'), 'ntf_notice_read', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_read_updated_by'), 'ntf_notice_read', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_read_user_id'), 'ntf_notice_read', 'sys_user', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_target_created_by'), 'ntf_notice_target', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_target_notice_id'), 'ntf_notice_target', 'ntf_notice', ['notice_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_target_org_id'), 'ntf_notice_target', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_target_role_id'), 'ntf_notice_target', 'sys_role', ['role_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_target_updated_by'), 'ntf_notice_target', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notice_target_user_id'), 'ntf_notice_target', 'sys_user', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notification_created_by'), 'ntf_notification', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notification_org_id'), 'ntf_notification', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notification_scene_id'), 'ntf_notification', 'ntf_scene', ['scene_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_notification_updated_by'), 'ntf_notification', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_preference_created_by'), 'ntf_preference', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_preference_scene_id'), 'ntf_preference', 'ntf_scene', ['scene_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_preference_updated_by'), 'ntf_preference', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_preference_user_id'), 'ntf_preference', 'sys_user', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_recipient_created_by'), 'ntf_recipient', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_recipient_notification_id'), 'ntf_recipient', 'ntf_notification', ['notification_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_recipient_org_id'), 'ntf_recipient', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_recipient_updated_by'), 'ntf_recipient', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_recipient_user_id'), 'ntf_recipient', 'sys_user', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_route_created_by'), 'ntf_route', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_route_deleted_by'), 'ntf_route', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_route_permission_id'), 'ntf_route', 'sys_permission', ['permission_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_route_role_id'), 'ntf_route', 'sys_role', ['role_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_route_scene_id'), 'ntf_route', 'ntf_scene', ['scene_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_route_updated_by'), 'ntf_route', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_route_user_id'), 'ntf_route', 'sys_user', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_scene_created_by'), 'ntf_scene', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_scene_deleted_by'), 'ntf_scene', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_scene_updated_by'), 'ntf_scene', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_scene_channel_created_by'), 'ntf_scene_channel', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_scene_channel_scene_id'), 'ntf_scene_channel', 'ntf_scene', ['scene_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_scene_channel_updated_by'), 'ntf_scene_channel', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_template_created_by'), 'ntf_template', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_template_deleted_by'), 'ntf_template', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_template_scene_id'), 'ntf_template', 'ntf_scene', ['scene_id'], ['id'])
    op.create_foreign_key(op.f('fk_ntf_template_updated_by'), 'ntf_template', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_department_created_by'), 'sys_department', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_department_deleted_by'), 'sys_department', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_department_manager_user_id'), 'sys_department', 'sys_user', ['manager_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_department_org_id'), 'sys_department', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_department_parent_id'), 'sys_department', 'sys_department', ['parent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_department_supervisor_party_id'), 'sys_department', 'md_person', ['supervisor_party_id'], ['party_id'])
    op.create_foreign_key(op.f('fk_sys_department_updated_by'), 'sys_department', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_dict_created_by'), 'sys_dict', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_dict_deleted_by'), 'sys_dict', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_dict_updated_by'), 'sys_dict', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_dict_item_created_by'), 'sys_dict_item', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_dict_item_deleted_by'), 'sys_dict_item', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_dict_item_dict_id'), 'sys_dict_item', 'sys_dict', ['dict_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_dict_item_updated_by'), 'sys_dict_item', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_job_created_by'), 'sys_job', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_job_deleted_by'), 'sys_job', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_job_org_id'), 'sys_job', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_job_updated_by'), 'sys_job', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_menu_created_by'), 'sys_menu', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_menu_deleted_by'), 'sys_menu', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_menu_parent_id'), 'sys_menu', 'sys_menu', ['parent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_menu_permission_id'), 'sys_menu', 'sys_permission', ['permission_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_menu_updated_by'), 'sys_menu', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_miniapp_menu_created_by'), 'sys_miniapp_menu', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_miniapp_menu_deleted_by'), 'sys_miniapp_menu', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_miniapp_menu_updated_by'), 'sys_miniapp_menu', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_org_created_by'), 'sys_org', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_org_deleted_by'), 'sys_org', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_org_parent_id'), 'sys_org', 'sys_org', ['parent_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_org_updated_by'), 'sys_org', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_permission_created_by'), 'sys_permission', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_permission_deleted_by'), 'sys_permission', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_permission_updated_by'), 'sys_permission', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_position_created_by'), 'sys_position', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_position_deleted_by'), 'sys_position', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_position_department_id'), 'sys_position', 'sys_department', ['department_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_position_job_id'), 'sys_position', 'sys_job', ['job_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_position_org_id'), 'sys_position', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_position_parent_position_id'), 'sys_position', 'sys_position', ['parent_position_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_position_updated_by'), 'sys_position', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_created_by'), 'sys_role', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_deleted_by'), 'sys_role', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_updated_by'), 'sys_role', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_menu_created_by'), 'sys_role_menu', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_menu_menu_id'), 'sys_role_menu', 'sys_menu', ['menu_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_menu_role_id'), 'sys_role_menu', 'sys_role', ['role_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_menu_updated_by'), 'sys_role_menu', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_miniapp_menu_created_by'), 'sys_role_miniapp_menu', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_miniapp_menu_miniapp_menu_id'), 'sys_role_miniapp_menu', 'sys_miniapp_menu', ['miniapp_menu_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_miniapp_menu_role_id'), 'sys_role_miniapp_menu', 'sys_role', ['role_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_miniapp_menu_updated_by'), 'sys_role_miniapp_menu', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_permission_created_by'), 'sys_role_permission', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_permission_permission_id'), 'sys_role_permission', 'sys_permission', ['permission_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_permission_role_id'), 'sys_role_permission', 'sys_role', ['role_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_role_permission_updated_by'), 'sys_role_permission', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_setting_created_by'), 'sys_setting', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_setting_deleted_by'), 'sys_setting', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_setting_updated_by'), 'sys_setting', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_auth_user_id'), 'sys_user', 'auth_user', ['auth_user_id'], ['id'], referent_schema='public')
    op.create_foreign_key(op.f('fk_sys_user_created_by'), 'sys_user', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_deleted_by'), 'sys_user', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_department_id'), 'sys_user', 'sys_department', ['department_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_org_id'), 'sys_user', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_updated_by'), 'sys_user', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_org_created_by'), 'sys_user_org', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_org_org_id'), 'sys_user_org', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_org_updated_by'), 'sys_user_org', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_org_user_id'), 'sys_user_org', 'sys_user', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_role_created_by'), 'sys_user_role', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_role_role_id'), 'sys_user_role', 'sys_role', ['role_id'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_role_updated_by'), 'sys_user_role', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_sys_user_role_user_id'), 'sys_user_role', 'sys_user', ['user_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_cc_record_created_by'), 'wf_cc_record', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_cc_record_instance_id'), 'wf_cc_record', 'wf_instance', ['instance_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_cc_record_org_id'), 'wf_cc_record', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_cc_record_recipient_user_id'), 'wf_cc_record', 'sys_user', ['recipient_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_cc_record_task_id'), 'wf_cc_record', 'wf_task', ['task_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_cc_record_updated_by'), 'wf_cc_record', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_definition_created_by'), 'wf_definition', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_definition_current_version_id'), 'wf_definition', 'wf_definition_version', ['current_version_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_definition_deleted_by'), 'wf_definition', 'sys_user', ['deleted_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_definition_org_id'), 'wf_definition', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_definition_updated_by'), 'wf_definition', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_definition_version_created_by'), 'wf_definition_version', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_definition_version_definition_id'), 'wf_definition_version', 'wf_definition', ['definition_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_definition_version_updated_by'), 'wf_definition_version', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_instance_created_by'), 'wf_instance', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_instance_definition_id'), 'wf_instance', 'wf_definition', ['definition_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_instance_org_id'), 'wf_instance', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_instance_started_by'), 'wf_instance', 'sys_user', ['started_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_instance_updated_by'), 'wf_instance', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_instance_version_id'), 'wf_instance', 'wf_definition_version', ['version_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_assignee_user_id'), 'wf_task', 'sys_user', ['assignee_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_completed_by'), 'wf_task', 'sys_user', ['completed_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_created_by'), 'wf_task', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_instance_id'), 'wf_task', 'wf_instance', ['instance_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_org_id'), 'wf_task', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_updated_by'), 'wf_task', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_action_actor_user_id'), 'wf_task_action', 'sys_user', ['actor_user_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_action_created_by'), 'wf_task_action', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_action_instance_id'), 'wf_task_action', 'wf_instance', ['instance_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_action_org_id'), 'wf_task_action', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_action_task_id'), 'wf_task_action', 'wf_task', ['task_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_candidate_created_by'), 'wf_task_candidate', 'sys_user', ['created_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_candidate_org_id'), 'wf_task_candidate', 'sys_org', ['org_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_candidate_task_id'), 'wf_task_candidate', 'wf_task', ['task_id'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_candidate_updated_by'), 'wf_task_candidate', 'sys_user', ['updated_by'], ['id'])
    op.create_foreign_key(op.f('fk_wf_task_candidate_user_id'), 'wf_task_candidate', 'sys_user', ['user_id'], ['id'])
    op.create_index(op.f('idx_ai_resource_active_bundle_id'), 'ai_resource_active', ['bundle_id'], unique=False)
    op.create_index(op.f('idx_audit_operation_log_actor_user_id'), 'audit_operation_log', ['actor_user_id'], unique=False)
    op.create_index(op.f('idx_audit_operation_log_org_id'), 'audit_operation_log', ['org_id'], unique=False)
    op.create_index('idx_file_attachment_business', 'file_attachment', ['business_type_code', 'business_id', 'scene_code'], unique=False)
    op.create_index(op.f('idx_file_attachment_business_sub_id'), 'file_attachment', ['business_sub_id'], unique=False)
    op.create_index('idx_file_attachment_status_code_expires_at', 'file_attachment', ['status_code', 'expires_at'], unique=False)
    op.create_index(op.f('idx_file_attachment_uploader_user_id'), 'file_attachment', ['uploader_user_id'], unique=False)
    op.create_index('uk_file_attachment_storage_key', 'file_attachment', ['storage_key'], unique=True)
    op.create_index(op.f('idx_md_person_user_id'), 'md_person', ['user_id'], unique=False)
    op.create_index(op.f('idx_md_person_contact_party_id'), 'md_person_contact', ['party_id'], unique=False)
    op.create_index(op.f('idx_md_person_pii_party_id'), 'md_person_pii', ['party_id'], unique=False)
    op.create_index('uk_md_person_pii_identity_type_code_identity_no_hash', 'md_person_pii', ['identity_type_code', 'identity_no_hash'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_ntf_channel_binding_user_id'), 'ntf_channel_binding', ['user_id'], unique=False)
    op.create_index('uk_ntf_channel_binding_channel_code_provider_code_appid_externa', 'ntf_channel_binding', ['channel_code', 'provider_code', 'appid', 'external_user_no'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_ntf_delivery_log_org_id'), 'ntf_delivery_log', ['org_id'], unique=False)
    op.create_index(op.f('idx_ntf_delivery_log_recipient_id'), 'ntf_delivery_log', ['recipient_id'], unique=False)
    op.create_index(op.f('idx_ntf_event_log_org_id'), 'ntf_event_log', ['org_id'], unique=False)
    op.create_index(op.f('idx_ntf_event_log_scene_id'), 'ntf_event_log', ['scene_id'], unique=False)
    op.create_index(op.f('idx_ntf_notice_org_id'), 'ntf_notice', ['org_id'], unique=False)
    op.create_index(op.f('idx_ntf_notice_published_by'), 'ntf_notice', ['published_by'], unique=False)
    op.create_index(op.f('idx_ntf_notice_read_org_id'), 'ntf_notice_read', ['org_id'], unique=False)
    op.create_index(op.f('idx_ntf_notice_read_user_id'), 'ntf_notice_read', ['user_id'], unique=False)
    op.create_index('uk_ntf_notice_read_notice_id_user_id', 'ntf_notice_read', ['notice_id', 'user_id'], unique=True)
    op.create_index(op.f('idx_ntf_notice_target_notice_id'), 'ntf_notice_target', ['notice_id'], unique=False)
    op.create_index(op.f('idx_ntf_notice_target_org_id'), 'ntf_notice_target', ['org_id'], unique=False)
    op.create_index(op.f('idx_ntf_notice_target_role_id'), 'ntf_notice_target', ['role_id'], unique=False)
    op.create_index(op.f('idx_ntf_notice_target_user_id'), 'ntf_notice_target', ['user_id'], unique=False)
    op.create_index(op.f('idx_ntf_notification_org_id'), 'ntf_notification', ['org_id'], unique=False)
    op.create_index(op.f('idx_ntf_notification_scene_id'), 'ntf_notification', ['scene_id'], unique=False)
    op.create_index('uk_ntf_notification_event_key', 'ntf_notification', ['event_key'], unique=True)
    op.create_index(op.f('idx_ntf_preference_scene_id'), 'ntf_preference', ['scene_id'], unique=False)
    op.create_index('uk_ntf_preference_user_id_scene_id_channel_code', 'ntf_preference', ['user_id', 'scene_id', 'channel_code'], unique=True)
    op.create_index(op.f('idx_ntf_recipient_org_id'), 'ntf_recipient', ['org_id'], unique=False)
    op.create_index(op.f('idx_ntf_recipient_user_id'), 'ntf_recipient', ['user_id'], unique=False)
    op.create_index('uk_ntf_recipient_notification_id_user_id', 'ntf_recipient', ['notification_id', 'user_id'], unique=True)
    op.create_index(op.f('idx_ntf_route_permission_id'), 'ntf_route', ['permission_id'], unique=False)
    op.create_index(op.f('idx_ntf_route_role_id'), 'ntf_route', ['role_id'], unique=False)
    op.create_index(op.f('idx_ntf_route_scene_id'), 'ntf_route', ['scene_id'], unique=False)
    op.create_index(op.f('idx_ntf_route_user_id'), 'ntf_route', ['user_id'], unique=False)
    op.create_index('uk_ntf_scene_scene_key', 'ntf_scene', ['scene_key'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index('uk_ntf_scene_channel_scene_id_channel_code', 'ntf_scene_channel', ['scene_id', 'channel_code'], unique=True)
    op.create_index('uk_ntf_template_scene_id_channel_code', 'ntf_template', ['scene_id', 'channel_code'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_sys_department_manager_user_id'), 'sys_department', ['manager_user_id'], unique=False)
    op.create_index(op.f('idx_sys_department_parent_id'), 'sys_department', ['parent_id'], unique=False)
    op.create_index(op.f('idx_sys_department_supervisor_party_id'), 'sys_department', ['supervisor_party_id'], unique=False)
    op.create_index('uk_sys_department_org_id_department_no', 'sys_department', ['org_id', 'department_no'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index('uk_sys_dict_dict_code', 'sys_dict', ['dict_code'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index('uk_sys_dict_item_dict_id_item_code', 'sys_dict_item', ['dict_id', 'item_code'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_sys_job_org_id'), 'sys_job', ['org_id'], unique=False)
    op.create_index('uk_sys_job_org_id_job_no', 'sys_job', ['org_id', 'job_no'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_sys_menu_parent_id'), 'sys_menu', ['parent_id'], unique=False)
    op.create_index(op.f('idx_sys_menu_permission_id'), 'sys_menu', ['permission_id'], unique=False)
    op.create_index('uk_sys_menu_menu_key', 'sys_menu', ['menu_key'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index('uk_sys_miniapp_menu_portal_code_menu_key', 'sys_miniapp_menu', ['portal_code', 'menu_key'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_sys_org_parent_id'), 'sys_org', ['parent_id'], unique=False)
    op.create_index('uk_sys_org_org_no', 'sys_org', ['org_no'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index('uk_sys_permission_permission_key', 'sys_permission', ['permission_key'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_sys_position_department_id'), 'sys_position', ['department_id'], unique=False)
    op.create_index(op.f('idx_sys_position_job_id'), 'sys_position', ['job_id'], unique=False)
    op.create_index(op.f('idx_sys_position_org_id'), 'sys_position', ['org_id'], unique=False)
    op.create_index(op.f('idx_sys_position_parent_position_id'), 'sys_position', ['parent_position_id'], unique=False)
    op.create_index('uk_sys_position_department_head', 'sys_position', ['department_id'], unique=True, postgresql_where=sa.text('is_department_head and deleted_at is null'))
    op.create_index('uk_sys_position_org_id_position_no', 'sys_position', ['org_id', 'position_no'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index('uk_sys_role_role_no', 'sys_role', ['role_no'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_sys_role_menu_menu_id'), 'sys_role_menu', ['menu_id'], unique=False)
    op.create_index('uk_sys_role_menu_role_id_menu_id', 'sys_role_menu', ['role_id', 'menu_id'], unique=True)
    op.create_index(op.f('idx_sys_role_miniapp_menu_miniapp_menu_id'), 'sys_role_miniapp_menu', ['miniapp_menu_id'], unique=False)
    op.create_index('uk_sys_role_miniapp_menu_role_id_miniapp_menu_id', 'sys_role_miniapp_menu', ['role_id', 'miniapp_menu_id'], unique=True)
    op.create_index(op.f('idx_sys_role_permission_permission_id'), 'sys_role_permission', ['permission_id'], unique=False)
    op.create_index('uk_sys_role_permission_role_id_permission_id', 'sys_role_permission', ['role_id', 'permission_id'], unique=True)
    op.create_index('uk_sys_setting_setting_key', 'sys_setting', ['setting_key'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_sys_user_department_id'), 'sys_user', ['department_id'], unique=False)
    op.create_index(op.f('idx_sys_user_org_id'), 'sys_user', ['org_id'], unique=False)
    op.create_index('uk_sys_user_auth_user_id', 'sys_user', ['auth_user_id'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index(op.f('idx_sys_user_org_org_id'), 'sys_user_org', ['org_id'], unique=False)
    op.create_index('uk_sys_user_org_user_id_org_id', 'sys_user_org', ['user_id', 'org_id'], unique=True)
    op.create_index(op.f('idx_sys_user_role_role_id'), 'sys_user_role', ['role_id'], unique=False)
    op.create_index('uk_sys_user_role_user_id_role_id', 'sys_user_role', ['user_id', 'role_id'], unique=True)
    op.create_index(op.f('idx_wf_cc_record_instance_id'), 'wf_cc_record', ['instance_id'], unique=False)
    op.create_index(op.f('idx_wf_cc_record_org_id'), 'wf_cc_record', ['org_id'], unique=False)
    op.create_index(op.f('idx_wf_cc_record_recipient_user_id'), 'wf_cc_record', ['recipient_user_id'], unique=False)
    op.create_index(op.f('idx_wf_cc_record_task_id'), 'wf_cc_record', ['task_id'], unique=False)
    op.create_index(op.f('idx_wf_definition_current_version_id'), 'wf_definition', ['current_version_id'], unique=False)
    op.create_index(op.f('idx_wf_definition_org_id'), 'wf_definition', ['org_id'], unique=False)
    op.create_index('uk_wf_definition_definition_no', 'wf_definition', ['definition_no'], unique=True, postgresql_where=sa.text('deleted_at is null'))
    op.create_index('uk_wf_definition_version_definition_id_version_no', 'wf_definition_version', ['definition_id', 'version_no'], unique=True)
    op.create_index(op.f('idx_wf_instance_definition_id'), 'wf_instance', ['definition_id'], unique=False)
    op.create_index(op.f('idx_wf_instance_org_id'), 'wf_instance', ['org_id'], unique=False)
    op.create_index(op.f('idx_wf_instance_started_by'), 'wf_instance', ['started_by'], unique=False)
    op.create_index(op.f('idx_wf_instance_version_id'), 'wf_instance', ['version_id'], unique=False)
    op.create_index(op.f('idx_wf_task_assignee_user_id'), 'wf_task', ['assignee_user_id'], unique=False)
    op.create_index(op.f('idx_wf_task_completed_by'), 'wf_task', ['completed_by'], unique=False)
    op.create_index(op.f('idx_wf_task_instance_id'), 'wf_task', ['instance_id'], unique=False)
    op.create_index(op.f('idx_wf_task_org_id'), 'wf_task', ['org_id'], unique=False)
    op.create_index(op.f('idx_wf_task_action_actor_user_id'), 'wf_task_action', ['actor_user_id'], unique=False)
    op.create_index(op.f('idx_wf_task_action_instance_id'), 'wf_task_action', ['instance_id'], unique=False)
    op.create_index(op.f('idx_wf_task_action_org_id'), 'wf_task_action', ['org_id'], unique=False)
    op.create_index(op.f('idx_wf_task_action_task_id'), 'wf_task_action', ['task_id'], unique=False)
    op.create_index(op.f('idx_wf_task_candidate_org_id'), 'wf_task_candidate', ['org_id'], unique=False)
    op.create_index(op.f('idx_wf_task_candidate_user_id'), 'wf_task_candidate', ['user_id'], unique=False)
    op.create_index('uk_wf_task_candidate_task_id_user_id', 'wf_task_candidate', ['task_id', 'user_id'], unique=True)
    # ### end Alembic commands ###


def downgrade():
    # Tables first, then foreign keys, to support audit reference cycles.
    op.drop_constraint(op.f('fk_wf_task_candidate_user_id'), 'wf_task_candidate', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_candidate_updated_by'), 'wf_task_candidate', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_candidate_task_id'), 'wf_task_candidate', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_candidate_org_id'), 'wf_task_candidate', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_candidate_created_by'), 'wf_task_candidate', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_action_task_id'), 'wf_task_action', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_action_org_id'), 'wf_task_action', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_action_instance_id'), 'wf_task_action', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_action_created_by'), 'wf_task_action', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_action_actor_user_id'), 'wf_task_action', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_updated_by'), 'wf_task', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_org_id'), 'wf_task', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_instance_id'), 'wf_task', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_created_by'), 'wf_task', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_completed_by'), 'wf_task', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_task_assignee_user_id'), 'wf_task', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_instance_version_id'), 'wf_instance', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_instance_updated_by'), 'wf_instance', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_instance_started_by'), 'wf_instance', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_instance_org_id'), 'wf_instance', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_instance_definition_id'), 'wf_instance', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_instance_created_by'), 'wf_instance', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_definition_version_updated_by'), 'wf_definition_version', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_definition_version_definition_id'), 'wf_definition_version', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_definition_version_created_by'), 'wf_definition_version', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_definition_updated_by'), 'wf_definition', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_definition_org_id'), 'wf_definition', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_definition_deleted_by'), 'wf_definition', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_definition_current_version_id'), 'wf_definition', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_definition_created_by'), 'wf_definition', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_cc_record_updated_by'), 'wf_cc_record', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_cc_record_task_id'), 'wf_cc_record', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_cc_record_recipient_user_id'), 'wf_cc_record', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_cc_record_org_id'), 'wf_cc_record', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_cc_record_instance_id'), 'wf_cc_record', type_='foreignkey')
    op.drop_constraint(op.f('fk_wf_cc_record_created_by'), 'wf_cc_record', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_role_user_id'), 'sys_user_role', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_role_updated_by'), 'sys_user_role', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_role_role_id'), 'sys_user_role', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_role_created_by'), 'sys_user_role', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_org_user_id'), 'sys_user_org', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_org_updated_by'), 'sys_user_org', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_org_org_id'), 'sys_user_org', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_org_created_by'), 'sys_user_org', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_updated_by'), 'sys_user', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_org_id'), 'sys_user', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_department_id'), 'sys_user', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_deleted_by'), 'sys_user', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_created_by'), 'sys_user', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_user_auth_user_id'), 'sys_user', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_setting_updated_by'), 'sys_setting', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_setting_deleted_by'), 'sys_setting', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_setting_created_by'), 'sys_setting', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_permission_updated_by'), 'sys_role_permission', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_permission_role_id'), 'sys_role_permission', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_permission_permission_id'), 'sys_role_permission', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_permission_created_by'), 'sys_role_permission', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_miniapp_menu_updated_by'), 'sys_role_miniapp_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_miniapp_menu_role_id'), 'sys_role_miniapp_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_miniapp_menu_miniapp_menu_id'), 'sys_role_miniapp_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_miniapp_menu_created_by'), 'sys_role_miniapp_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_menu_updated_by'), 'sys_role_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_menu_role_id'), 'sys_role_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_menu_menu_id'), 'sys_role_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_menu_created_by'), 'sys_role_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_updated_by'), 'sys_role', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_deleted_by'), 'sys_role', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_role_created_by'), 'sys_role', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_position_updated_by'), 'sys_position', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_position_parent_position_id'), 'sys_position', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_position_org_id'), 'sys_position', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_position_job_id'), 'sys_position', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_position_department_id'), 'sys_position', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_position_deleted_by'), 'sys_position', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_position_created_by'), 'sys_position', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_permission_updated_by'), 'sys_permission', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_permission_deleted_by'), 'sys_permission', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_permission_created_by'), 'sys_permission', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_org_updated_by'), 'sys_org', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_org_parent_id'), 'sys_org', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_org_deleted_by'), 'sys_org', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_org_created_by'), 'sys_org', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_miniapp_menu_updated_by'), 'sys_miniapp_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_miniapp_menu_deleted_by'), 'sys_miniapp_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_miniapp_menu_created_by'), 'sys_miniapp_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_menu_updated_by'), 'sys_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_menu_permission_id'), 'sys_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_menu_parent_id'), 'sys_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_menu_deleted_by'), 'sys_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_menu_created_by'), 'sys_menu', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_job_updated_by'), 'sys_job', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_job_org_id'), 'sys_job', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_job_deleted_by'), 'sys_job', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_job_created_by'), 'sys_job', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_dict_item_updated_by'), 'sys_dict_item', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_dict_item_dict_id'), 'sys_dict_item', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_dict_item_deleted_by'), 'sys_dict_item', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_dict_item_created_by'), 'sys_dict_item', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_dict_updated_by'), 'sys_dict', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_dict_deleted_by'), 'sys_dict', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_dict_created_by'), 'sys_dict', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_department_updated_by'), 'sys_department', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_department_supervisor_party_id'), 'sys_department', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_department_parent_id'), 'sys_department', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_department_org_id'), 'sys_department', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_department_manager_user_id'), 'sys_department', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_department_deleted_by'), 'sys_department', type_='foreignkey')
    op.drop_constraint(op.f('fk_sys_department_created_by'), 'sys_department', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_template_updated_by'), 'ntf_template', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_template_scene_id'), 'ntf_template', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_template_deleted_by'), 'ntf_template', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_template_created_by'), 'ntf_template', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_scene_channel_updated_by'), 'ntf_scene_channel', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_scene_channel_scene_id'), 'ntf_scene_channel', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_scene_channel_created_by'), 'ntf_scene_channel', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_scene_updated_by'), 'ntf_scene', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_scene_deleted_by'), 'ntf_scene', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_scene_created_by'), 'ntf_scene', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_route_user_id'), 'ntf_route', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_route_updated_by'), 'ntf_route', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_route_scene_id'), 'ntf_route', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_route_role_id'), 'ntf_route', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_route_permission_id'), 'ntf_route', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_route_deleted_by'), 'ntf_route', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_route_created_by'), 'ntf_route', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_recipient_user_id'), 'ntf_recipient', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_recipient_updated_by'), 'ntf_recipient', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_recipient_org_id'), 'ntf_recipient', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_recipient_notification_id'), 'ntf_recipient', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_recipient_created_by'), 'ntf_recipient', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_preference_user_id'), 'ntf_preference', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_preference_updated_by'), 'ntf_preference', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_preference_scene_id'), 'ntf_preference', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_preference_created_by'), 'ntf_preference', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notification_updated_by'), 'ntf_notification', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notification_scene_id'), 'ntf_notification', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notification_org_id'), 'ntf_notification', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notification_created_by'), 'ntf_notification', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_target_user_id'), 'ntf_notice_target', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_target_updated_by'), 'ntf_notice_target', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_target_role_id'), 'ntf_notice_target', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_target_org_id'), 'ntf_notice_target', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_target_notice_id'), 'ntf_notice_target', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_target_created_by'), 'ntf_notice_target', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_read_user_id'), 'ntf_notice_read', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_read_updated_by'), 'ntf_notice_read', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_read_org_id'), 'ntf_notice_read', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_read_notice_id'), 'ntf_notice_read', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_read_created_by'), 'ntf_notice_read', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_updated_by'), 'ntf_notice', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_published_by'), 'ntf_notice', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_org_id'), 'ntf_notice', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_deleted_by'), 'ntf_notice', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_notice_created_by'), 'ntf_notice', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_event_log_scene_id'), 'ntf_event_log', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_event_log_org_id'), 'ntf_event_log', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_event_log_created_by'), 'ntf_event_log', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_delivery_log_recipient_id'), 'ntf_delivery_log', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_delivery_log_org_id'), 'ntf_delivery_log', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_delivery_log_created_by'), 'ntf_delivery_log', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_channel_binding_user_id'), 'ntf_channel_binding', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_channel_binding_updated_by'), 'ntf_channel_binding', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_channel_binding_deleted_by'), 'ntf_channel_binding', type_='foreignkey')
    op.drop_constraint(op.f('fk_ntf_channel_binding_created_by'), 'ntf_channel_binding', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_pii_updated_by'), 'md_person_pii', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_pii_party_id'), 'md_person_pii', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_pii_deleted_by'), 'md_person_pii', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_pii_created_by'), 'md_person_pii', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_contact_updated_by'), 'md_person_contact', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_contact_party_id'), 'md_person_contact', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_contact_deleted_by'), 'md_person_contact', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_contact_created_by'), 'md_person_contact', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_user_id'), 'md_person', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_updated_by'), 'md_person', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_photo_file_id'), 'md_person', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_party_id'), 'md_person', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_deleted_by'), 'md_person', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_person_created_by'), 'md_person', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_party_updated_by'), 'md_party', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_party_deleted_by'), 'md_party', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_party_created_by'), 'md_party', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_organization_updated_by'), 'md_organization', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_organization_party_id'), 'md_organization', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_organization_deleted_by'), 'md_organization', type_='foreignkey')
    op.drop_constraint(op.f('fk_md_organization_created_by'), 'md_organization', type_='foreignkey')
    op.drop_constraint(op.f('fk_int_outbox_event_updated_by'), 'int_outbox_event', type_='foreignkey')
    op.drop_constraint(op.f('fk_int_outbox_event_created_by'), 'int_outbox_event', type_='foreignkey')
    op.drop_constraint(op.f('fk_file_attachment_uploader_user_id'), 'file_attachment', type_='foreignkey')
    op.drop_constraint(op.f('fk_file_attachment_updated_by'), 'file_attachment', type_='foreignkey')
    op.drop_constraint(op.f('fk_file_attachment_org_id'), 'file_attachment', type_='foreignkey')
    op.drop_constraint(op.f('fk_file_attachment_created_by'), 'file_attachment', type_='foreignkey')
    op.drop_constraint(op.f('fk_audit_operation_log_org_id'), 'audit_operation_log', type_='foreignkey')
    op.drop_constraint(op.f('fk_audit_operation_log_created_by'), 'audit_operation_log', type_='foreignkey')
    op.drop_constraint(op.f('fk_audit_operation_log_actor_user_id'), 'audit_operation_log', type_='foreignkey')
    op.drop_constraint(op.f('fk_ai_resource_document_updated_by'), 'ai_resource_document', type_='foreignkey')
    op.drop_constraint(op.f('fk_ai_resource_document_created_by'), 'ai_resource_document', type_='foreignkey')
    op.drop_constraint(op.f('fk_ai_resource_document_bundle_id'), 'ai_resource_document', type_='foreignkey')
    op.drop_constraint(op.f('fk_ai_resource_bundle_updated_by'), 'ai_resource_bundle', type_='foreignkey')
    op.drop_constraint(op.f('fk_ai_resource_bundle_created_by'), 'ai_resource_bundle', type_='foreignkey')
    op.drop_constraint(op.f('fk_ai_resource_active_updated_by'), 'ai_resource_active', type_='foreignkey')
    op.drop_constraint(op.f('fk_ai_resource_active_created_by'), 'ai_resource_active', type_='foreignkey')
    op.drop_constraint(op.f('fk_ai_resource_active_bundle_id'), 'ai_resource_active', type_='foreignkey')
    op.drop_table('wf_task_candidate')
    op.drop_table('wf_task_action')
    op.drop_table('wf_task')
    op.drop_table('wf_instance')
    op.drop_table('wf_definition_version')
    op.drop_table('wf_definition')
    op.drop_table('wf_cc_record')
    op.drop_table('sys_user_role')
    op.drop_table('sys_user_org')
    op.drop_table('sys_user')
    op.drop_table('sys_setting')
    op.drop_table('sys_role_permission')
    op.drop_table('sys_role_miniapp_menu')
    op.drop_table('sys_role_menu')
    op.drop_table('sys_role')
    op.drop_table('sys_position')
    op.drop_table('sys_permission')
    op.drop_table('sys_org')
    op.drop_table('sys_miniapp_menu')
    op.drop_table('sys_menu')
    op.drop_table('sys_job')
    op.drop_table('sys_dict_item')
    op.drop_table('sys_dict')
    op.drop_table('sys_department')
    op.drop_table('ntf_template')
    op.drop_table('ntf_scene_channel')
    op.drop_table('ntf_scene')
    op.drop_table('ntf_route')
    op.drop_table('ntf_recipient')
    op.drop_table('ntf_preference')
    op.drop_table('ntf_notification')
    op.drop_table('ntf_notice_target')
    op.drop_table('ntf_notice_read')
    op.drop_table('ntf_notice')
    op.drop_table('ntf_event_log')
    op.drop_table('ntf_delivery_log')
    op.drop_table('ntf_channel_binding')
    op.drop_table('md_person_pii')
    op.drop_table('md_person_contact')
    op.drop_table('md_person')
    op.drop_table('md_party')
    op.drop_table('md_organization')
    op.drop_table('int_outbox_event')
    op.drop_table('file_attachment')
    op.drop_table('audit_operation_log')
    op.drop_table('ai_resource_document')
    op.drop_table('ai_resource_bundle')
    op.drop_table('ai_resource_active')
    # ### end Alembic commands ###
