"""插件配置声明、公开模板与环境读取；不导入业务模块或修改进程环境。"""
from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path, PurePosixPath
import re
from typing import TypeVar

from dotenv.parser import parse_stream
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsError

ROOT = Path(__file__).resolve().parents[5]
SettingsType = TypeVar("SettingsType", bound=BaseSettings)


@dataclass(frozen=True)
class PluginConfiguration:
    env_prefix: str
    template: str
    secret_keys: tuple[str, ...] = ()


def is_private_plugin_configuration(name: str, key: str, configuration: PluginConfiguration | None) -> bool:
    """仅允许声明的公开模板；其余 dotenv 文件不作为业务源码分发。"""
    template = f"plugins/{key}/{configuration.template}" if configuration else None
    if name == template:
        return False
    return any(part.lower().startswith(".env") for part in PurePosixPath(name).parts) or name.lower().endswith(".env")


def _safe_child(root: Path, relative: str) -> Path:
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink() or path.is_junction():
            raise ValueError("插件配置路径不能使用链接")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("插件配置路径不能越界")
    return path


def _environment_values(path: Path, prefix: str) -> dict[str, str | None]:
    values = {}
    for row in parse_stream(StringIO(path.read_text(encoding="utf-8"))):
        if row.error:
            raise ValueError(f"插件配置格式无效（第 {row.original.line} 行）")
        if row.key is None:
            continue
        if not re.fullmatch(re.escape(prefix) + r"[A-Z][A-Z0-9_]*", row.key):
            raise ValueError("插件配置变量必须使用声明的前缀和大写字母、数字、下划线")
        if row.key in values:
            raise ValueError("插件配置变量不能重复")
        values[row.key] = row.value
    return values


def read_plugin_configuration(directory: Path, key: str, document: object) -> PluginConfiguration:
    """校验插件自己的变量命名空间和模板；模板中的凭据必须留空。"""
    required = {"env_prefix", "template"}
    if not isinstance(document, dict) or not required <= document.keys() or document.keys() - required - {"secret_keys"}:
        raise ValueError(f"{key}: configuration 字段无效")
    prefix = key.upper() + "_"
    if document["env_prefix"] != prefix or document["template"] != "config/.env.example":
        raise ValueError(f"{key}: configuration 必须声明前缀 {prefix} 和模板 config/.env.example")
    secrets = document.get("secret_keys", [])
    if not isinstance(secrets, list) or any(not isinstance(name, str) or not re.fullmatch(re.escape(prefix) + r"[A-Z][A-Z0-9_]*", name) for name in secrets) or len(set(secrets)) != len(secrets):
        raise ValueError(f"{key}: secret_keys 必须是本插件完整变量名且不能重复")
    configuration = PluginConfiguration(prefix, document["template"], tuple(secrets))
    template = _safe_child(directory, configuration.template)
    if not template.is_file():
        raise ValueError(f"{key}: 缺少插件配置模板 config/.env.example")
    values = _environment_values(template, prefix)
    if not set(secrets) <= values.keys():
        raise ValueError(f"{key}: 配置模板缺少声明的凭据变量")
    sensitive = set(secrets) | {name for name in values if re.search(r"_(?:KEY|TOKEN|SECRET|PASSWORD)$", name)}
    if any(values[name] for name in sensitive):
        raise ValueError(f"{key}: 配置模板中的凭据必须留空，不能随包发布")
    return configuration


def load_plugin_settings(key: str, settings_type: type[SettingsType]) -> SettingsType:
    """读取已部署插件配置：进程环境 > 独立 env > 旧 backend/.env > 类型默认值。

    未部署插件不读取本地配置文件；允许离线工具显式构造其参数模型。
    配置类型的 env_prefix 必须位于清单声明的命名空间内。
    """
    from app.framework.deployment import selected_plugin_keys
    from app.framework.plugin_manifest import read_plugin_manifest

    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        raise ValueError("插件配置 key 无效")
    manifest = read_plugin_manifest(ROOT / "plugins" / key / "plugin.toml")
    configuration = manifest.configuration
    if configuration is None:
        raise ValueError(f"{key}: 请先在 plugin.toml 声明 configuration")
    prefix = settings_type.model_config.get("env_prefix", "")
    if not prefix.startswith(configuration.env_prefix):
        raise ValueError(f"{key}: 配置类型的 env_prefix 超出插件命名空间")
    files = None
    if key in selected_plugin_keys():
        local = _safe_child(ROOT, f"plugins/core/backend/config/plugin/{key}.env")
        if local.exists():
            _environment_values(local, configuration.env_prefix)
        legacy = _safe_child(ROOT, "plugins/core/backend/.env")
        files = (legacy, local)
    try:
        return settings_type(_env_file=files, _env_file_encoding="utf-8")
    except ValidationError as error:
        fields = ", ".join(".".join(map(str, row["loc"])) for row in error.errors(include_input=False))
        raise ValueError(f"{key}: 插件配置值无效，请检查字段 {fields}") from None
    except SettingsError:
        raise ValueError(f"{key}: 插件配置无法解析，请检查变量格式") from None
