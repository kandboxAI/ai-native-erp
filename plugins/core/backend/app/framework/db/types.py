"""Stable migration types that do not depend on the tenant search_path."""
from pgvector.sqlalchemy import Vector


class PublicVector(Vector):
    """pgvector is installed once in public; tenant migrations exclude public."""
    cache_ok = True

    def get_col_spec(self, **kw):
        return "public." + super().get_col_spec(**kw)
