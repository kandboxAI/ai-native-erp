"""插件配置的优先级、部署隔离及源码包边界；不访问数据库或外部服务。"""
import hashlib
import json
import os
from pathlib import Path
import zipfile

from dotenv import dotenv_values
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
import pytest

from app.framework import deployment, plugin_settings
from app.framework.plugin_manifest import read_plugin_manifest
from app.framework.plugin_package import HEADER, inspect_package, install_package, pack_plugin
from app.framework.plugin_scaffold import scaffold_plugin


def foundation(path):
    path.mkdir()
    (path / "deployment.json").write_text('{"format_version":1,"plugins":[]}', encoding="utf-8")
    (path / "miniprogram/src").mkdir(parents=True)
    (path / "miniprogram/src/pages.json").write_text('{"pages":[{"path":"pages/home/index"}]}', encoding="utf-8")
    return path


class SampleSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SAMPLE_APP_", extra="ignore")
    request_timeout_seconds: int = Field(default=30, ge=1, le=300)
    api_key: SecretStr = SecretStr("")


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = foundation(tmp_path / "source")
    scaffold_plugin(root, "sample_app", "示例", "L3", [])
    monkeypatch.setattr(plugin_settings, "ROOT", root)
    monkeypatch.setattr(deployment, "selected_plugin_keys", lambda: ("sample_app",))
    monkeypatch.delenv("SAMPLE_APP_REQUEST_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("SAMPLE_APP_API_KEY", raising=False)
    return root


def local_file(root):
    path = root / "plugins/core/backend/config/plugin/sample_app.env"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_settings_precedence_and_no_environment_mutation(source, monkeypatch):
    legacy = source / "plugins/core/backend/.env"
    legacy.write_text("SAMPLE_APP_REQUEST_TIMEOUT_SECONDS=40\n", encoding="utf-8")
    assert plugin_settings.load_plugin_settings("sample_app", SampleSettings).request_timeout_seconds == 40
    local = local_file(source)
    local.write_text("SAMPLE_APP_REQUEST_TIMEOUT_SECONDS=50\nSAMPLE_APP_API_KEY=private-test-value\n", encoding="utf-8")
    before = dict(os.environ)
    config = plugin_settings.load_plugin_settings("sample_app", SampleSettings)
    assert config.request_timeout_seconds == 50
    assert config.api_key.get_secret_value() == "private-test-value"
    assert dict(os.environ) == before
    monkeypatch.setenv("SAMPLE_APP_REQUEST_TIMEOUT_SECONDS", "60")
    assert plugin_settings.load_plugin_settings("sample_app", SampleSettings).request_timeout_seconds == 60
    local.unlink()
    legacy.unlink()
    monkeypatch.delenv("SAMPLE_APP_REQUEST_TIMEOUT_SECONDS")
    assert plugin_settings.load_plugin_settings("sample_app", SampleSettings).request_timeout_seconds == 30


def test_undeployed_plugin_does_not_read_local_files(source, monkeypatch):
    (source / "plugins/core/backend/.env").write_text("SAMPLE_APP_REQUEST_TIMEOUT_SECONDS=80\n", encoding="utf-8")
    local_file(source).write_text("JWT_SECRET=must-not-be-read\n", encoding="utf-8")
    monkeypatch.setattr(deployment, "selected_plugin_keys", lambda: ())
    assert plugin_settings.load_plugin_settings("sample_app", SampleSettings).request_timeout_seconds == 30


@pytest.mark.parametrize("original,replacement", [
    ('env_prefix = "SAMPLE_APP_"', 'env_prefix = "MES_"'),
    ('template = "config/.env.example"', 'template = "../.env"'),
    ('secret_keys = []', 'secret_keys = ["LLM_GATEWAY_DEEPSEEK_API_KEY"]'),
    ('secret_keys = []', 'secret_keys = ["SAMPLE_APP_API_KEY", "SAMPLE_APP_API_KEY"]'),
    ('secret_keys = []', 'secret_keys = ["SAMPLE_APP_API_KEY"]'),
])
def test_manifest_rejects_invalid_configuration(source, original, replacement):
    path = source / "plugins/sample_app/plugin.toml"
    path.write_text(path.read_text(encoding="utf-8").replace(original, replacement), encoding="utf-8")
    with pytest.raises(ValueError):
        read_plugin_manifest(path)


@pytest.mark.parametrize("extra", [
    "SAMPLE_APP_API_KEY=not-public\n",
    "JWT_SECRET=not-public\n",
    "SAMPLE_APP_REQUEST_TIMEOUT_SECONDS=31\n",
    'SAMPLE_APP_BAD="unterminated\n',
])
def test_template_rejects_credentials_wrong_namespace_and_invalid_syntax(source, extra):
    template = source / "plugins/sample_app/config/.env.example"
    template.write_text(template.read_text(encoding="utf-8") + extra, encoding="utf-8")
    with pytest.raises(ValueError) as failure:
        read_plugin_manifest(source / "plugins/sample_app/plugin.toml")
    assert "not-public" not in str(failure.value)


def test_local_settings_validate_prefix_and_do_not_echo_rejected_values(source):
    path = local_file(source)
    path.write_text("OTHER_TIMEOUT=5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="前缀"):
        plugin_settings.load_plugin_settings("sample_app", SampleSettings)
    path.write_text("SAMPLE_APP_REQUEST_TIMEOUT_SECONDS=private-invalid-value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="request_timeout_seconds") as failure:
        plugin_settings.load_plugin_settings("sample_app", SampleSettings)
    assert "private-invalid-value" not in str(failure.value)
    with pytest.raises(ValueError, match="命名空间"):
        plugin_settings.load_plugin_settings("sample_app", BaseSettings)


def test_pack_install_and_upgrade_keep_template_but_preserve_private_configuration(source, tmp_path):
    private = source / "plugins/sample_app/.env"
    private.write_text("SAMPLE_APP_API_KEY=not-for-package\n", encoding="utf-8")
    (private.parent / "config/sample_app.env").write_text(private.read_text(encoding="utf-8"), encoding="utf-8")
    local_file(source).write_text(private.read_text(encoding="utf-8"), encoding="utf-8")
    package = tmp_path / "plugin.zip"
    pack_plugin(source, "sample_app", package, source_only=True)
    template = "plugins/sample_app/config/.env.example"
    with zipfile.ZipFile(package) as archive:
        assert template in archive.namelist()
        assert not any(b"not-for-package" in archive.read(name) for name in archive.namelist())
    target = foundation(tmp_path / "target")
    local = local_file(target)
    local.write_text("SAMPLE_APP_API_KEY=keep-local\n", encoding="utf-8")
    install_package(target, package, source_only=True)
    assert (target / template).is_file()
    (source / template).write_text("SAMPLE_APP_REQUEST_TIMEOUT_SECONDS=31\n", encoding="utf-8")
    package = tmp_path / "upgrade.zip"
    pack_plugin(source, "sample_app", package, source_only=True)
    install_package(target, package, source_only=True)
    assert (target / template).read_text(encoding="utf-8") == "SAMPLE_APP_REQUEST_TIMEOUT_SECONDS=31\n"
    assert local.read_text(encoding="utf-8") == "SAMPLE_APP_API_KEY=keep-local\n"


@pytest.mark.parametrize("name,content", [
    ("plugins/sample_app/.env", b"SAMPLE_APP_API_KEY=private"),
    ("plugins/sample_app/config/production.env", b"SAMPLE_APP_API_KEY=private"),
    ("plugins/sample_app/config/.env.example", b"SAMPLE_APP_API_KEY=private"),
])
def test_import_rejects_environment_files_and_secret_templates_even_with_valid_hashes(source, tmp_path, name, content):
    package = tmp_path / "plugin.zip"
    pack_plugin(source, "sample_app", package, source_only=True)
    with zipfile.ZipFile(package) as archive:
        contents = {entry: archive.read(entry) for entry in archive.namelist()}
    header = json.loads(contents[HEADER])
    header["files"][name] = hashlib.sha256(content).hexdigest()
    contents[name] = content
    contents[HEADER] = json.dumps(header).encode()
    with zipfile.ZipFile(package, "w") as archive:
        for entry, data in contents.items():
            archive.writestr(entry, data)
    with pytest.raises(ValueError):
        inspect_package(source, package)


def test_mes_template_covers_every_cnc_setting_without_credentials():
    root = Path(__file__).resolve().parents[4]
    if not (root / "plugins/mes/plugin.toml").is_file():
        pytest.skip("纯底座未安装 MES")
    from app.modules.mes.cnc.config import Settings

    manifest = read_plugin_manifest(root / "plugins/mes/plugin.toml")
    values = dotenv_values(root / "plugins/mes" / manifest.configuration.template)
    assert set(values) == {"MES_CNC_" + name.upper() for name in Settings.model_fields}
    assert all(not values[name] for name in manifest.configuration.secret_keys)
    assert not (root / "plugins/core/backend/config/plugin/mes.env").is_file() or "plugins/core/backend/config/plugin/*.env" in (root / ".gitignore").read_text(encoding="utf-8")
