"""表模型（md_party、md_person、md_person_pii、md_person_contact、md_organization）。

初始版本由 docs/foundation-platform/data-dictionary/tools/gen_models.py 按数据字典生成，之后以本文件为准维护。
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    bool_field,
    created_at_field,
    deleted_at_field,
    flex_form_field,
    id_field,
    updated_at_field,
)


class MdParty(SQLModel, table=True):
    """主体：一行为一个参与业务的主体（自然人或机构）。"""

    __tablename__ = "md_party"
    __table_args__ = (
        {'comment': '主体：一行为一个参与业务的主体（自然人或机构）。人员和外部机构的共同父表。'},
    )

    id: UUID = id_field()
    party_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '主体类型；字典 md_party_type'})
    display_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '显示名称'})
    is_active: bool = bool_field('是否有效', default=True)
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class MdPerson(SQLModel, table=True):
    """人员：一行为一个人（终身一条）。"""

    __tablename__ = "md_person"
    __table_args__ = (
        {'comment': '人员：一行为一个人（终身一条）。子类型表，主键为 `party_id`。学生、教师、监护人都通过 `party_id` 关联到这里。'},
    )

    party_id: UUID = Field(primary_key=True, foreign_key="md_party.id", nullable=False, sa_column_kwargs={'comment': '主体 ID；主键兼外键，引用 md_party.id'})
    full_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '姓名；敏感：个人'})
    gender_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '性别；字典 md_gender'})
    birth_date: date | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '出生日期；敏感：个人'})
    user_id: UUID | None = Field(default=None, foreign_key="sys_user.id", index=True, nullable=True, sa_column_kwargs={'comment': '租户内用户；有账号的人才有；本租户内唯一'})
    photo_file_id: UUID | None = Field(default=None, foreign_key="file_attachment.id", nullable=True, sa_column_kwargs={'comment': '照片文件；敏感：个人；引用 file_attachment'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class MdPersonPii(SQLModel, table=True):
    """人员身份信息：一行为一个人的一种证件（personal identity information）。"""

    __tablename__ = "md_person_pii"
    __table_args__ = (
        Index("uk_md_person_pii_identity_type_code_identity_no_hash", "identity_type_code", "identity_no_hash", unique=True, postgresql_where=text("deleted_at is null")),
        {'comment': '人员身份信息：一行为一个人的一种证件（personal identity information）。人员身份信息（personal identity information）：证件类机密信息，单独授权，加密存储。AI 和报表不可读取。'},
    )

    id: UUID = id_field()
    party_id: UUID = Field(foreign_key="md_person.party_id", index=True, nullable=False, sa_column_kwargs={'comment': '人员'})
    identity_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '证件类型；字典 md_identity_type'})
    identity_no_encrypted: str = Field(sa_type=Text, nullable=False, sa_column_kwargs={'comment': '证件号（密文）；敏感：机密'})
    identity_no_hash: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '证件号哈希；敏感：机密；用于精确查找与去重'})
    identity_no_masked: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '证件号（脱敏）；敏感：机密；如 3501**********1234'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class MdPersonContact(SQLModel, table=True):
    """人员联系方式：一行为一个人的一个联系方式。"""

    __tablename__ = "md_person_contact"
    __table_args__ = (
        {'comment': '人员联系方式：一行为一个人的一个联系方式。一人可有多个手机号、住址等；登录手机号在 `public.auth_user`，与这里含义不同。'},
    )

    id: UUID = id_field()
    party_id: UUID = Field(foreign_key="md_person.party_id", index=True, nullable=False, sa_column_kwargs={'comment': '人员'})
    contact_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '联系方式类型；字典 md_contact_type'})
    contact_value: str = Field(max_length=512, nullable=False, sa_column_kwargs={'comment': '联系方式；敏感：个人'})
    contact_value_hash: str | None = Field(default=None, max_length=128, nullable=True, sa_column_kwargs={'comment': '联系方式哈希；按手机号查人用'})
    purpose_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '用途；字典 md_contact_purpose'})
    is_primary: bool = bool_field('是否主要联系方式', default=False)
    is_verified: bool = bool_field('是否已验证', default=False)
    verified_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '验证时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')


class MdOrganization(SQLModel, table=True):
    """外部机构：一行为一个与业务往来的外部机构。"""

    __tablename__ = "md_organization"
    __table_args__ = (
        {'comment': '外部机构：一行为一个与业务往来的外部机构。生源学校、实习企业、供应商等外部机构；不是本租户的组织架构（那是 `sys_org`）。子类型表，主键为 `party_id`。'},
    )

    party_id: UUID = Field(primary_key=True, foreign_key="md_party.id", nullable=False, sa_column_kwargs={'comment': '主体 ID；主键兼外键，引用 md_party.id'})
    legal_name: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '法定名称'})
    credit_no: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '统一社会信用代码'})
    organization_type_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '机构类型；字典 md_organization_type'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('创建人；系统任务创建时为空')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    deleted_at: datetime | None = deleted_at_field()
    deleted_by: UUID | None = audit_user_field('删除人；与删除时间同时出现')
    flex_form: dict[str, Any] = flex_form_field('扩展字段；租户自定义字段，结构见动态表单定义；默认 {}')

