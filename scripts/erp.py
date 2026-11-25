"""Cross-platform repository entry point; always use backend's virtual environment."""
from pathlib import Path
import os
import subprocess
import sys


def interpreter(root: Path, platform: str = os.name) -> Path:
    return root / "plugins/core/backend" / ".venv" / ("Scripts/python.exe" if platform == "nt" else "bin/python")


def main(argv=None) -> int:
    root = Path(__file__).resolve().parents[1]
    python = interpreter(root)
    if not python.is_file():
        print("请先创建 plugins/core/backend/.venv 并安装 plugins/core/backend/requirements.txt 中的依赖。", file=sys.stderr)
        print("Windows: python -m venv plugins/core/backend/.venv", file=sys.stderr)
        print("Linux:   python3 -m venv plugins/core/backend/.venv", file=sys.stderr)
        return 2
    env = dict(os.environ)
    env.pop("ERP_DEPLOYMENT_PROFILE", None)
    env.pop("DEPLOYMENT_PROFILE", None)
    return subprocess.run(
        [str(python), "-X", "utf8", "-m", "app.framework.workspace_cli", *(sys.argv[1:] if argv is None else argv)],
        cwd=root / "plugins/core/backend", shell=False, env=env,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
