# 文件与附件设计

底座的文件模块统一管理上传、绑定、鉴权下载和回收。`file_attachment` 保存文件元数据，文件内容保存在配置的存储后端。业务表可用外键引用单文件，或按业务类型、记录 ID 和场景读取多个附件。

## 上传与读取

| 操作 | 接口与条件 |
| --- | --- |
| 申请上传 | `POST /api/files/upload-tickets` 提交场景、文件名、内容类型、字节数和 Base64 编码的 `content_md5`。服务端校验场景限制，创建 `uploading` 记录并返回签名上传地址。 |
| 上传内容 | 客户端向签名地址发送 PUT 请求，使用约定的 `Content-Type` 和 `Content-MD5` 请求头。 |
| 完成上传 | `POST /api/files/{file_id}/complete` 校验存储对象，校验通过后状态变为 `pending`。 |
| 绑定单据 | 业务 Service 在事务中调用 `FileService.bind` 或 `replace`，校验上传人、文件状态及场景，通过后关联业务记录并标记为 `bound`。 |
| 下载或预览 | `GET /api/files/{file_id}/url` 按附件状态和绑定业务的访问规则校验，签发临时下载地址。 |
| 丢弃未用文件 | `DELETE /api/files/{file_id}` 供上传人丢弃未绑定附件，后台清理任务回收逾期的上传和待绑定文件。 |

本地开发和对象存储使用同一套签名地址协议。开发环境的上传与下载通过后端本地存储适配器完成。

## 插件接入

- 在所属模块用 `register_file_scene` 登记文件场景、允许类型、文件大小和数量。文件列表和绑定复用 `FileService`。
- 用 `register_file_access` 为业务类型登记访问校验。已绑定文件随业务单据鉴权，未登记访问规则时拒绝读取。文件接口不返回上传人。
- 使用文件做文档分析时，通过文件模块的受限读取接口获取原件。存储键、签名地址和敏感文件内容不直接加入 AI 查询目录。
- 验证上传、绑定、预览、访问拒绝和逾期清理。旧存储数据迁移前核对涉及的业务记录和文件引用，按[数据库维护](../database-workflow.md)审查升级方案。

实现入口见[文件 API](../../backend/app/modules/file/api.py)、[文件服务](../../backend/app/modules/file/service.py)与[文件模型](../../backend/app/modules/file/models.py)。
