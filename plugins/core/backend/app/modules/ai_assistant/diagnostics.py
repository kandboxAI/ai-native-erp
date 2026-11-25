"""仅记录故障类别与代码位置，不记录 SDK 原始异常、凭据或业务内容。"""
import re
import traceback
from pathlib import Path


def failure_info(error):
    if isinstance(error, FileNotFoundError) and error.filename and Path(error.filename).name in {"node", "node.exe"}:
        return "DSH_NODE_NOT_FOUND", "FastAPI 服务进程找不到 Node.js，请检查 SERVER_ASSISTANT_NODE_BIN 或服务的 PATH 配置"
    if isinstance(error, PermissionError):
        return "DSH_PERMISSION_DENIED", "智能体运行权限不足，请检查运行目录与 Node.js 的访问权限"
    # 只识别固定信号；SDK 文本可能混有工具结果，不向日志或客户端透传。
    text = str(error)
    if any(marker in text for marker in ("bad option: --import", "Promise.withResolvers is not a function")):
        return "DSH_NODE_INCOMPATIBLE", "DSH 使用的 Node.js 版本不兼容，请配置 Node 22.19+（22 系列）或 24+ 的可执行文件路径"
    if any(marker in text for marker in ("ERR_MODULE_NOT_FOUND", "MODULE_NOT_FOUND", "Cannot find package")):
        return "DSH_DEPENDENCY_MISSING", "DSH 运行依赖缺失，请在 DSH 仓库安装依赖并重新构建"
    if isinstance(error, TypeError) and "unexpected keyword argument" in text:
        return "DSH_SDK_INCOMPATIBLE", "DSH Python SDK 与后端不兼容，请重新安装仓库中的 SDK"
    if 'no adapter registered for provider "erp-gateway"' in text:
        return "DSH_ERP_PROVIDER_UNAVAILABLE", "DSH 的 ERP 模型提供器未注册，请检查服务端集成适配与 Harness 构建产物"
    return "RUNTIME_FAILED", "智能体运行失败，请检查 DSH 配置和模型网关后重试"


def log_failure(logger, error, *, run_id, phase):
    code, message = failure_info(error)
    safe_phase = phase if phase in {"preparing", "initializing", "running"} else "unknown"
    if code == "RUNTIME_FAILED" and safe_phase == "initializing" and type(error).__name__ == "TransportClosedError":
        code, message = "DSH_INITIALIZATION_FAILED", "DSH 初始化时进程退出，请管理员检查服务使用的 Node.js、依赖及运行目录权限"
    # SDK 在 stderr tail 前写入进程退出码；只提取数字，不发布原始 stderr。
    header = str(error).split("stderr tail:", 1)[0]
    match = re.search(r"(?:^|\n)exit code: (-?\d{1,3})(?:\n|$)", header)
    exit_code = int(match.group(1)) if match else "unknown"
    frames = ">".join(f"{frame.name}:{frame.lineno}" for frame in traceback.extract_tb(error.__traceback__)[-6:])
    logger.error("智能体运行失败 run_id=%s phase=%s code=%s exception=%s exit_code=%s frames=%s",
                 run_id, safe_phase, code, type(error).__name__, exit_code, frames)
    return code, message
