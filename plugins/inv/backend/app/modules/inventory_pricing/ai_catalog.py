"""采购价默认不向 AI 发布表、读接口或写接口。"""
from app.framework.ai_catalog import AiProvider

PROVIDER = AiProvider(domain="inventory_pricing", resources=())
