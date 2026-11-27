# 许可证范围

根目录 `LICENSE` 中的 MIT 许可证适用于管理底座、`plugins/inv/` 库存插件、`plugins/mes/` 制造插件和 `plugins/sample_app/` 快盒插件、插件清单声明的公开接口与基线文件，以及它们的公开构建、接入工具和随发行物提供的文档、测试。inv、MES、快盒目录各自保留一份 `LICENSE`，打包后仍携带 MIT 声明。

底座发行范围由 `core_manifest.json`、底座页面依赖闭包及 `backend/scripts/core_source_allowlist.json` 确定，文件及 SHA-256 见发行版 `source-manifest.json`。纯底座导出不携带业务插件；MES 套件独立交付 inv、MES 和各自已发布基线，插件文件摘要见包清单。

授权范围不包含 EDU 及其内部教育业务、其他未明确授权的插件、私有备份、客户配置、真实业务数据、图纸、模型和附件。开发目录或 Git 历史中存在某个文件，不意味着该文件纳入本次开源授权。本地环境增量迁移、检索快照和构建产物不属于源码发行物。

第三方代码继续适用原有许可证及版权声明，尤其保留 `web/LICENSE` 中 pure-admin 的 MIT 声明。
