"""
Monitor de Stock (Inventario)
"""
from typing import Dict, Any

from automations.monitors.base_monitor import BaseMonitor
from automations.database import execute_query
from app.utils.logger import logger


class StockMonitor(BaseMonitor):
    """Monitorea niveles de stock/inventario"""
    
    async def check(self) -> Dict[str, Any]:
        """
        Obtiene el estado actual del inventario
        """
        query = """
            SELECT 
                id,
                product_name,
                sku,
                category,
                quantity,
                unit,
                min_stock,
                last_updated
            FROM inventory
            ORDER BY product_name
        """
        
        try:
            inventory_items = await execute_query(query)
        except Exception as e:
            logger.warning(f"⚠️ No se pudo consultar inventario: {e}")
            logger.info("💡 Ejecuta setup_inventory.sql para crear la tabla")
            return {}
        
        inventory_dict = {
            str(item['id']): item for item in inventory_items
        }
        
        logger.debug(f"📦 {len(inventory_items)} productos en inventario")
        
        return inventory_dict
    
    async def detect_changes(self, current_state: Dict[str, Any]) -> None:
        """
        Detecta cambios en el inventario y envía notificaciones
        """
        if self.last_state is None:
            await self._check_current_levels(current_state)
            return
        
        for item_id, current_item in current_state.items():
            last_item = self.last_state.get(item_id)
            
            if last_item:
                await self._check_stock_change(last_item, current_item)
            else:
                logger.info(f"➕ Nuevo producto: {current_item.get('product_name')}")
    
    async def _check_current_levels(self, inventory: Dict[str, Any]):
        """Verifica los niveles actuales de stock (primera ejecución)"""
        thresholds = self.config.get('thresholds', {})
        low_stock_threshold = thresholds.get('low_stock', 5)
        critical_stock_threshold = thresholds.get('critical_stock', 2)
        
        low_stock_items = []
        critical_stock_items = []
        out_of_stock_items = []
        
        for item in inventory.values():
            quantity = item.get('quantity', 0)
            product_name = item.get('product_name', 'N/A')
            min_stock = item.get('min_stock', low_stock_threshold)
            
            if quantity == 0:
                out_of_stock_items.append(product_name)
            elif quantity <= critical_stock_threshold or quantity <= min_stock / 2:
                critical_stock_items.append(f"{product_name} (quedan {quantity})")
            elif quantity <= low_stock_threshold or quantity <= min_stock:
                low_stock_items.append(f"{product_name} (quedan {quantity})")
        
        if out_of_stock_items or critical_stock_items or low_stock_items:
            message = "📦 *Resumen de Stock Inicial*\n\n"
            
            if out_of_stock_items:
                message += "🔴 *Sin Stock:*\n"
                message += "\n".join(f"• {item}" for item in out_of_stock_items)
                message += "\n\n"
            
            if critical_stock_items:
                message += "🟠 *Stock Crítico:*\n"
                message += "\n".join(f"• {item}" for item in critical_stock_items)
                message += "\n\n"
            
            if low_stock_items:
                message += "🟡 *Stock Bajo:*\n"
                message += "\n".join(f"• {item}" for item in low_stock_items)
            
            priority = "critical" if out_of_stock_items else "high" if critical_stock_items else "medium"
            
            await self.send_notification(
                message=message.strip(),
                priority=priority
            )
    
    async def _check_stock_change(self, last_item: Dict, current_item: Dict):
        """Verifica cambios en un producto específico"""
        last_qty = last_item.get('quantity', 0)
        current_qty = current_item.get('quantity', 0)
        
        if last_qty == current_qty:
            return
        
        thresholds = self.config.get('thresholds', {})
        low_stock_threshold = thresholds.get('low_stock', 5)
        critical_stock_threshold = thresholds.get('critical_stock', 2)
        min_stock = current_item.get('min_stock', low_stock_threshold)
        
        # Stock se acabó
        if current_qty == 0 and last_qty > 0:
            if self.config.get('notifications', {}).get('out_of_stock', True):
                await self._notify_out_of_stock(current_item, last_qty)
        
        # Stock crítico
        elif current_qty <= critical_stock_threshold and last_qty > critical_stock_threshold:
            if self.config.get('notifications', {}).get('critical_stock', True):
                await self._notify_critical_stock(current_item)
        
        # Stock bajo
        elif current_qty <= low_stock_threshold and last_qty > low_stock_threshold:
            if self.config.get('notifications', {}).get('low_stock', True):
                await self._notify_low_stock(current_item)
        
        # Stock restaurado
        elif current_qty > min_stock and last_qty <= min_stock:
            if self.config.get('notifications', {}).get('stock_restored', True):
                await self._notify_stock_restored(current_item, last_qty, current_qty)
    
    async def _notify_out_of_stock(self, item: Dict, last_qty: int):
        """Notifica cuando un producto se queda sin stock"""
        message = f"""🔴 *PRODUCTO SIN STOCK*

📦 Producto: {item.get('product_name', 'N/A')}
🏷️ SKU: {item.get('sku', 'N/A')}
📂 Categoría: {item.get('category', 'N/A')}
📊 Cantidad anterior: {last_qty} {item.get('unit', 'unidades')}

⚠️ *REQUIERE REPOSICIÓN URGENTE*
        """.strip()
        
        await self.send_notification(message=message, priority="critical")
        logger.warning(f"🔴 SIN STOCK: {item.get('product_name')}")
    
    async def _notify_critical_stock(self, item: Dict):
        """Notifica cuando el stock llega a nivel crítico"""
        message = f"""🟠 *STOCK CRÍTICO*

📦 Producto: {item.get('product_name', 'N/A')}
🏷️ SKU: {item.get('sku', 'N/A')}
📊 Cantidad: {item.get('quantity', 0)} {item.get('unit', 'unidades')}

⚠️ Por favor, reabastecer pronto
        """.strip()
        
        await self.send_notification(message=message, priority="high")
        logger.warning(f"🟠 STOCK CRÍTICO: {item.get('product_name')}")
    
    async def _notify_low_stock(self, item: Dict):
        """Notifica cuando el stock está bajo"""
        message = f"""🟡 *Stock Bajo*

📦 Producto: {item.get('product_name', 'N/A')}
📊 Cantidad: {item.get('quantity', 0)} {item.get('unit', 'unidades')}
📌 Stock mínimo: {item.get('min_stock', 'N/A')}

ℹ️ Considera reabastecer
        """.strip()
        
        await self.send_notification(message=message, priority="medium")
        logger.info(f"🟡 STOCK BAJO: {item.get('product_name')}")
    
    async def _notify_stock_restored(self, item: Dict, last_qty: int, current_qty: int):
        """Notifica cuando el stock se ha restaurado"""
        message = f"""✅ *Stock Restaurado*

📦 Producto: {item.get('product_name', 'N/A')}
📊 Cantidad: {last_qty} → {current_qty} {item.get('unit', 'unidades')}

👍 Stock restaurado a niveles normales
        """.strip()
        
        await self.send_notification(message=message, priority="low")
        logger.info(f"✅ STOCK RESTAURADO: {item.get('product_name')}")

