"""库存沿用既有 HTTP 策略；未登记表不会自动获得 SQL 查询能力。"""
from app.framework.ai_catalog import AiProvider

PROVIDER = AiProvider(domain="inventory", resources=(), inherit_http_policy=True)
