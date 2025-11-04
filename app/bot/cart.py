"""
Shopping Cart Manager - handles cart operations for reservations and extras
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import json

from app.db.connection import get_connection

logger = logging.getLogger(__name__)


@dataclass
class CartItem:
    """Represents an item in the shopping cart"""
    item_type: str  # 'reservation', 'extra', 'accommodation'
    name: str
    price: int  # Price in CLP
    quantity: int = 1
    metadata: Dict[str, Any] = None  # Additional info (date, time, capacity, etc.)
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            "item_type": self.item_type,
            "name": self.name,
            "price": self.price,
            "quantity": self.quantity,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CartItem':
        """Create from dictionary"""
        return cls(
            item_type=data.get("item_type"),
            name=data.get("name"),
            price=data.get("price", 0),
            quantity=data.get("quantity", 1),
            metadata=data.get("metadata", {})
        )


class CartManager:
    """Manages shopping carts for users"""
    
    # Extras catalog with prices
    EXTRAS_CATALOG = {
        "tabla grande": {"name": "Tabla de Picoteo Grande (4 personas)", "price": 25000},
        "tabla pequena": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "tabla pequeña": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "jugo": {"name": "Jugo Natural 1L", "price": 10000},
        "jugo natural": {"name": "Jugo Natural 1L", "price": 10000},
        "bebida": {"name": "Lata Bebida (Coca-Cola o Fanta)", "price": 2900},
        "agua": {"name": "Agua Mineral 1.5L", "price": 2500},
        "helado": {"name": "Helado Individual", "price": 3500},
        "modo romantico": {"name": "Modo Romántico", "price": 25000},
        "modo romántico": {"name": "Modo Romántico", "price": 25000},
        "velas": {"name": "Velas LED Decorativas", "price": 10000},
        "letras": {"name": "Letras Luminosas 'Te Amo' / 'Love'", "price": 15000},
        "pack nocturno": {"name": "Pack Nocturno Completo (velas + letras)", "price": 20000},
        "video 15": {"name": "Video Personalizado 15s", "price": 30000},
        "video 60": {"name": "Video Personalizado 60s", "price": 40000},
        "transporte": {"name": "Transporte Ida y Vuelta desde Pucón", "price": 50000},
        "toalla normal": {"name": "Toalla Normal", "price": 9000},
        "toalla poncho": {"name": "Toalla Poncho", "price": 10000},
        "chalas": {"name": "Chalas de Ducha", "price": 10000},
        "reserva flex": {"name": "Reserva FLEX (+10%)", "price": 0},  # Se calcula como % del total
    }
    
    # Prices per person based on capacity
    PRICES_PER_PERSON = {
        2: 69990,
        3: 54990,
        4: 44990,
        5: 38990,
        6: 32990,
        7: 29990,
    }
    
    def __init__(self):
        pass
    
    async def get_cart(self, phone_number: str) -> List[CartItem]:
        """Get user's cart from database"""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT cart_data, updated_at
                        FROM whatsapp_carts
                        WHERE phone_number = %s
                        ORDER BY updated_at DESC
                        LIMIT 1
                    """, (phone_number,))
                    
                    result = cur.fetchone()
                    
                    if result and result[0]:
                        # Parse JSON cart data
                        cart_data = json.loads(result[0]) if isinstance(result[0], str) else result[0]
                        return [CartItem.from_dict(item) for item in cart_data]
                    
                    return []
        except Exception as e:
            # Check if it's a "table does not exist" error
            error_msg = str(e).lower()
            if 'does not exist' in error_msg or 'relation' in error_msg:
                logger.warning(f"Cart table does not exist yet. Run migrations: {e}")
            else:
                logger.error(f"Error getting cart for {phone_number}: {e}")
            return []
    
    async def save_cart(self, phone_number: str, customer_name: str, items: List[CartItem]) -> bool:
        """Save cart to database"""
        try:
            cart_data = json.dumps([item.to_dict() for item in items])
            
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Upsert cart
                    cur.execute("""
                        INSERT INTO whatsapp_carts (phone_number, customer_name, cart_data, updated_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (phone_number) 
                        DO UPDATE SET 
                            cart_data = EXCLUDED.cart_data,
                            customer_name = EXCLUDED.customer_name,
                            updated_at = EXCLUDED.updated_at
                    """, (phone_number, customer_name, cart_data, datetime.now()))
                    
                    conn.commit()
                    logger.info(f"Cart saved for {phone_number}")
                    return True
        except Exception as e:
            # Check if it's a "table does not exist" error
            error_msg = str(e).lower()
            if 'does not exist' in error_msg or 'relation' in error_msg:
                logger.warning(f"Cart table does not exist yet. Run migrations to create whatsapp_carts table: {e}")
            else:
                logger.error(f"Error saving cart for {phone_number}: {e}")
            return False
    
    async def add_item(self, phone_number: str, customer_name: str, item: CartItem) -> bool:
        """Add item to cart"""
        cart = await self.get_cart(phone_number)
        
        # Check if reservation already exists (only one reservation per cart)
        if item.item_type == "reservation":
            cart = [i for i in cart if i.item_type != "reservation"]
        
        cart.append(item)
        return await self.save_cart(phone_number, customer_name, cart)
    
    async def remove_item(self, phone_number: str, customer_name: str, item_index: int) -> bool:
        """Remove item from cart by index"""
        cart = await self.get_cart(phone_number)
        
        if 0 <= item_index < len(cart):
            cart.pop(item_index)
            return await self.save_cart(phone_number, customer_name, cart)
        
        return False
    
    async def clear_cart(self, phone_number: str) -> bool:
        """Clear entire cart"""
        return await self.save_cart(phone_number, "", [])
    
    def calculate_total(self, items: List[CartItem]) -> int:
        """Calculate total price of cart items"""
        total = 0
        
        for item in items:
            if item.item_type == "reservation":
                # Reservation price is per person
                total += item.price * item.quantity
            elif item.item_type == "extra":
                if item.name == "Reserva FLEX (+10%)":
                    # FLEX is calculated as % of subtotal
                    subtotal = sum(i.price * i.quantity for i in items if i.item_type != "extra" or i.name != "Reserva FLEX (+10%)")
                    total += int(subtotal * 0.1)
                else:
                    total += item.price * item.quantity
            else:
                total += item.price * item.quantity
        
        return total
    
    def format_cart_message(self, items: List[CartItem]) -> str:
        """Format cart as a readable message"""
        if not items:
            return "🛒 Tu carrito está vacío, grumete ⚓\n\nEscribe *agregar* seguido del extra o servicio que quieras."
        
        message = "🛒 *Tu Carrito HotBoat*\n\n"
        
        total = 0
        reservation = None
        
        for i, item in enumerate(items):
            if item.item_type == "reservation":
                reservation = item
                price = item.price * item.quantity
                message += f"📅 *Reserva HotBoat*\n"
                message += f"   Fecha: {item.metadata.get('date', 'N/A')}\n"
                message += f"   Horario: {item.metadata.get('time', 'N/A')}\n"
                message += f"   Personas: {item.quantity}\n"
                message += f"   Precio: ${price:,}\n\n"
                total += price
            elif item.item_type == "extra":
                price = item.price * item.quantity
                if item.name == "Reserva FLEX (+10%)":
                    # FLEX will be calculated at the end
                    message += f"🔒 {item.name}\n"
                    message += f"   (Se aplica al subtotal)\n\n"
                else:
                    message += f"{i}. {item.name}\n"
                    message += f"   ${price:,} ({item.quantity}x ${item.price:,})\n\n"
                    total += price
        
        # Calculate FLEX if present
        if any(item.name == "Reserva FLEX (+10%)" for item in items):
            flex_amount = int(total * 0.1)
            total += flex_amount
            message = message.replace(
                "🔒 Reserva FLEX (+10%)\n   (Se aplica al subtotal)\n\n",
                f"🔒 Reserva FLEX (+10%)\n   ${flex_amount:,}\n\n"
            )
        
        message += f"━━━━━━━━━━━━━━━━\n"
        message += f"💰 *Total: ${total:,}*\n\n"
        message += f"📝 *Comandos:*\n"
        message += f"• *Eliminar [número]* - Eliminar un item\n"
        message += f"• *Confirmar* - Confirmar y proceder con el pago\n"
        message += f"• *Vaciar* - Vaciar carrito\n"
        
        return message
    
    def parse_extra_from_message(self, message: str) -> Optional[CartItem]:
        """Parse extra name from user message"""
        message_lower = message.lower().strip()
        
        # Remove common prefixes
        prefixes = ["agregar", "quiero", "necesito", "dame", "pon", "agrega"]
        for prefix in prefixes:
            if message_lower.startswith(prefix):
                message_lower = message_lower[len(prefix):].strip()
        
        # Try to match with catalog
        for key, value in self.EXTRAS_CATALOG.items():
            if key in message_lower:
                return CartItem(
                    item_type="extra",
                    name=value["name"],
                    price=value["price"],
                    quantity=1
                )
        
        return None
    
    def create_reservation_item(
        self,
        date: str,
        time: str,
        capacity: int,
        service_name: str = "HotBoat Trip"
    ) -> CartItem:
        """Create a reservation cart item"""
        price_per_person = self.PRICES_PER_PERSON.get(capacity, 69990)
        
        return CartItem(
            item_type="reservation",
            name=f"{service_name} - {capacity} personas",
            price=price_per_person,
            quantity=capacity,
            metadata={
                "date": date,
                "time": time,
                "capacity": capacity,
                "service_name": service_name
            }
        )

