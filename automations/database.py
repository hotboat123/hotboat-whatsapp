"""
Database utilities for automations
Reutiliza la conexión existente del proyecto
"""
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from app.db.connection import get_connection, init_db, close_db
from app.utils.logger import logger


async def execute_query(query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
    """
    Ejecuta una query SELECT y devuelve los resultados
    """
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            
            # Get column names
            columns = [desc[0] for desc in cur.description] if cur.description else []
            
            # Fetch all results
            rows = await cur.fetchall()
            
            # Convert to list of dicts
            return [dict(zip(columns, row)) for row in rows]


async def execute_single(query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
    """
    Ejecuta una query y devuelve un único resultado
    """
    results = await execute_query(query, params)
    return results[0] if results else None

