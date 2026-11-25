"""资产管理：场所数量资产、单件设备及其不可变变更历史。"""

# 模型收集和独立 CLI 初始化同样注册追踪，不依赖 HTTP 路由的导入顺序。
# 仅登记纯内存处理器，不访问数据库或执行初始化。
from . import stock_service as _stock_tracking
