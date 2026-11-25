"""文件与附件（L1）表模型：file_attachment。

一行为一个上传的文件及其业务绑定。文件本体在对象存储（客户端直传），这里只存元数据。
状态：uploading（已签发上传 URL）→ pending（已上传并核对，待业务绑定）→ bound（已绑定，不可复用）。
设计见 docs/foundation-platform/file-attachment-design.md §2.1。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, text
from sqlmodel import Field, SQLModel

from app.framework.db.models import (
    audit_user_field,
    created_at_field,
    flex_form_field,
    id_field,
    org_field,
    updated_at_field,
)

STATUS_UPLOADING = "uploading"
STATUS_PENDING = "pending"
STATUS_BOUND = "bound"


class FileAttachment(SQLModel, table=True):
    """文件与附件：一行为一个上传的文件。"""

    __tablename__ = "file_attachment"
    __table_args__ = (
        Index("uk_file_attachment_storage_key", "storage_key", unique=True),
        Index("idx_file_attachment_status_code_expires_at", "status_code", "expires_at"),
        Index("idx_file_attachment_business", "business_type_code", "business_id", "scene_code"),
        {'comment': '文件与附件：一行为一个上传的文件。uploading 表示等待客户端直传，pending 表示已上传、待业务绑定，bound 表示已绑定且不可复用。任何接口都不返回上传人。'},
    )

    id: UUID = id_field()
    org_id: UUID = org_field(index=False)
    uploader_user_id: UUID = Field(foreign_key="sys_user.id", index=True, nullable=False, sa_column_kwargs={'comment': '上传人；不对外返回'})
    storage_backend: str = Field(default="oss", max_length=16, nullable=False, sa_column_kwargs={'comment': '存储后端：oss 或 local（仅开发环境）'})
    storage_key: str = Field(max_length=512, nullable=False, sa_column_kwargs={'comment': '对象键：<租户 schema>/<场景>/<年>/<月>/<id>.<扩展名>'})
    original_file_name: str = Field(max_length=255, nullable=False, sa_column_kwargs={'comment': '原始文件名'})
    extension: str = Field(max_length=16, nullable=False, sa_column_kwargs={'comment': '扩展名'})
    content_type: str = Field(max_length=128, nullable=False, sa_column_kwargs={'comment': '内容类型'})
    file_kind_code: str = Field(max_length=16, nullable=False, sa_column_kwargs={'comment': '文件类别；字典 file_kind'})
    file_size: int = Field(sa_type=BigInteger, nullable=False, sa_column_kwargs={'comment': '文件大小（字节）；申请上传时声明，完成上传时按存储中的实际大小核对'})
    content_md5: str = Field(max_length=32, nullable=False, sa_column_kwargs={'comment': '内容 MD5（Base64）；客户端上传时带 Content-MD5，由存储校验完整性'})
    width: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '图片宽度；图片时填写'})
    height: int | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '图片高度；图片时填写'})
    status_code: str = Field(default=STATUS_UPLOADING, max_length=16, nullable=False, sa_column_kwargs={'comment': '状态；字典 file_attachment_status', "server_default": text("'uploading'")})
    scene_code: str = Field(max_length=64, nullable=False, sa_column_kwargs={'comment': '上传场景；决定允许的类型、大小与数量，由业务模块登记'})
    business_type_code: str | None = Field(default=None, max_length=64, nullable=True, sa_column_kwargs={'comment': '业务类型；取业务主表的表名，如 fac_patrol_record'})
    business_id: UUID | None = Field(default=None, nullable=True, sa_column_kwargs={'comment': '业务单据；多态引用，由业务类型决定所指的表'})
    business_sub_id: UUID | None = Field(default=None, index=True, nullable=True, sa_column_kwargs={'comment': '业务子单据；如报修的某条进度'})
    sort_no: int = Field(default=0, nullable=False, sa_column_kwargs={'comment': '排序', "server_default": text("0")})
    expires_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False, sa_column_kwargs={'comment': '过期时间；uploading、pending 超时后由清理任务删除记录和对象'})
    bound_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True), nullable=True, sa_column_kwargs={'comment': '绑定时间'})
    created_at: datetime = created_at_field()
    created_by: UUID | None = audit_user_field('上传人')
    updated_at: datetime = updated_at_field()
    updated_by: UUID | None = audit_user_field('修改人')
    flex_form: dict[str, Any] = flex_form_field()


__all__ = ["FileAttachment", "STATUS_BOUND", "STATUS_PENDING", "STATUS_UPLOADING"]
