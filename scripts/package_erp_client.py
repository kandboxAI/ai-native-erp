"""按 suite.toml 的 desktop 配置构建 ERP + DSH 客户端，不修改本地配置。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def release_environment(root: Path, suite_key: str, api_url: str, signed: bool, inherited=None):
    from urllib.parse import urlsplit
    sys.path.insert(0, str(root / "plugins/core/backend"))
    from app.framework.plugin_suite import read_suite
    if not re.fullmatch(r"[a-z][a-z0-9_]*", suite_key):
        raise ValueError("套件标识无效")
    directory = root / "plugins" / suite_key
    suite = read_suite(directory / "suite.toml")
    if suite.desktop is None:
        raise ValueError(f"请在 plugins/{suite_key}/suite.toml 配置 [desktop]")
    url = urlsplit(api_url)
    if (url.scheme != "https" and not (not signed and url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"})) or url.path not in {"", "/"} or url.query or url.fragment or url.username or url.password or not url.hostname:
        raise ValueError("后端地址须为 HTTPS 根地址；无签名测试包允许本机 HTTP，不附加 /api")
    desktop = dict(suite.desktop)
    if "icon" in desktop:
        icon = (directory / desktop["icon"]).resolve()
        if not icon.is_relative_to(directory.resolve()) or not icon.is_file():
            raise ValueError("客户端图标不存在或越出所属插件")
        content = icon.read_bytes()
        if not content.startswith(b"\x89PNG\r\n\x1a\n") or len(content) < 24:
            raise ValueError("客户端图标不是有效 PNG")
        width, height = int.from_bytes(content[16:20], "big"), int.from_bytes(content[20:24], "big")
        if width != height or width < 256:
            raise ValueError("客户端图标必须是至少 256×256 的正方形 PNG")
        desktop["icon"] = str(icon)
    # 使用现有品牌合并器，避免在桌面配置中再维护一份助手名称。
    node = shutil.which("node")
    if not node:
        raise ValueError("请安装 Node.js")
    code = "import {getProductBranding} from './product-branding.mjs'; console.log(JSON.stringify(getProductBranding(JSON.parse(process.argv[1]))));"
    deployment = json.loads((root / "deployment.json").read_text(encoding="utf-8"))
    if suite_key not in deployment["plugins"]:
        raise ValueError("请先通过 scripts/erp.py use 选择需要打包的套件")
    result = subprocess.run([node, "--input-type=module", "-e", code, json.dumps(deployment["plugins"])], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True)
    branding = json.loads(result.stdout)
    desktop["assistant_name"] = branding["assistant_name"]
    env = dict(os.environ if inherited is None else inherited)
    env["ERP_DIST_DIR"] = str((root / "plugins/core/web/dist").resolve())
    env["ERP_API_URL"] = api_url
    env["DSH_ERP_BRANDING"] = json.dumps(desktop, ensure_ascii=False)
    return env, desktop


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--harness-root", required=True, type=Path)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--arch", choices=["arm64", "x64"])
    parser.add_argument("--signed", action="store_true")
    parser.add_argument("--skip-web-build", action="store_true")
    parser.add_argument("--check", action="store_true", help="仅检查发行方案和调用参数，不构建、不访问数据库")
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", args.version):
            raise ValueError("客户端版本须为语义版本，不含 +build")
        harness = args.harness_root.resolve()
        seam = harness / "apps/desktop/scripts/desktop-erp-branding.mjs"
        if not seam.is_file():
            raise ValueError("请更新 Harness，当前版本不支持套件客户端品牌配置")
        env, desktop = release_environment(ROOT, args.suite, args.api_url, args.signed)
        platform = "win" if sys.platform == "win32" else "mac" if sys.platform == "darwin" else None
        if platform is None:
            raise ValueError("Windows 安装包在 Windows 构建，macOS 安装包在 macOS 构建")
        import platform as system_platform
        arch = args.arch or ("arm64" if system_platform.machine().lower() in {"arm64", "aarch64"} else "x64")
        if platform == "win" and arch != "x64":
            raise ValueError("当前 Windows 打包只支持 x64")
        pnpm = shutil.which("pnpm.cmd" if os.name == "nt" else "pnpm")
        if not pnpm:
            raise ValueError("请安装 pnpm")
        script = f"package:desktop:{platform}:{arch}" + ("" if args.signed else ":unsigned")
        command = [pnpm, "run", script, "--", "--build-version", args.version]
        print(json.dumps({"suite": args.suite, "product_name": desktop["product_name"], "assistant_name": desktop["assistant_name"], "app_id": desktop["app_id"], "artifact_prefix": desktop["artifact_prefix"], "client_version": args.version, "target": f"{platform}-{arch}"}, ensure_ascii=False, indent=2))
        if args.check:
            return 0
        if not args.skip_web_build:
            subprocess.run([pnpm, "build"], cwd=ROOT / "plugins/core/web", env=env, check=True)
        if not (ROOT / "plugins/core/web/dist/index.html").is_file():
            raise ValueError("缺少 plugins/core/web/dist/index.html，请先构建管理端")
        subprocess.run([*command, "--check"], cwd=harness, env=env, check=True)
        subprocess.run(command, cwd=harness, env=env, check=True)
        return 0
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as error:
        print(f"客户端打包已停止：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    preferred = ROOT / "plugins/core/backend/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if preferred.is_file() and Path(sys.executable).resolve() != preferred.resolve():
        raise SystemExit(subprocess.run([str(preferred), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]]).returncode)
    raise SystemExit(main())
