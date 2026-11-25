"""在当前后端解释器中安装配置所指向的 DSH 源码 SDK；不启动服务。"""
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.core.config import get_settings


def main():
    configured = get_settings().server_assistant_dsh_root
    if not configured:
        raise SystemExit("请先在 backend/.env 配置 SERVER_ASSISTANT_DSH_ROOT")
    sdk = Path(configured).expanduser().resolve() / "python/sdk"
    if not (sdk / "pyproject.toml").is_file():
        raise SystemExit("DSH SDK 目录不存在，请检查 SERVER_ASSISTANT_DSH_ROOT")
    environment = os.environ.copy()
    environment["SERVER_ASSISTANT_DSH_ROOT"] = str(sdk.parent.parent)
    result = subprocess.run([
        "uv", "pip", "install", "--python", sys.executable, "--no-deps",
        "-r", str(BACKEND / "requirements-server-assistant.txt"),
    ], env=environment, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
