"""仅检查服务端 DSH 初始化；请用 FastAPI 相同的运行用户及环境执行。"""
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fastapi import HTTPException
from app.core.config import get_settings
from app.modules.ai_assistant import diagnostics, runtime


def main():
    logging.basicConfig(level=logging.ERROR)
    settings = get_settings()
    print(f"Python: {sys.executable}", flush=True)
    node = shutil.which(settings.server_assistant_node_bin)
    print(f"Node 配置: {settings.server_assistant_node_bin}", flush=True)
    print(f"Node: {node or '未找到'}", flush=True)
    if node:
        try:
            result = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5)
            version = result.stdout.strip()
            # 仅打印版本号，不打印进程的原始输出或异常内容。
            print(f"Node 版本: {version if re.fullmatch(r'v\d+\.\d+\.\d+', version) else '无法识别'}", flush=True)
        except (OSError, subprocess.TimeoutExpired):
            print("Node 版本: 无法执行版本检查", flush=True)
    print(f"DSH: {settings.server_assistant_dsh_root or '未配置'}", flush=True)
    print(f"ERP 内部地址: {settings.server_assistant_api_url}", flush=True)
    print("检查 DSH 初始化；不发送模型请求或业务查询。", flush=True)
    try:
        runtime.check_startup()
    except HTTPException as error:
        print(f"检查失败：{error.detail}")
        return 1
    except Exception as error:
        code, message = diagnostics.log_failure(logging.getLogger(__name__), error,
                                                run_id="startup-check", phase="initializing")
        print(f"检查失败：{code}，{message}")
        return 1
    print("DSH 初始化检查通过。尚未验证模型网关、ERP 授权或检索索引。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
