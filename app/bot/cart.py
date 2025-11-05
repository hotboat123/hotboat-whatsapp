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
    
    # Extras catalog with prices (EXACTAMENTE como en el menú 4 del FAQ)
    EXTRAS_CATALOG = {
        # Tablas de Picoteo
        "tabla grande": {"name": "Tabla de Picoteo Grande (4 personas)", "price": 25000},
        "tabla de picoteo grande": {"name": "Tabla de Picoteo Grande (4 personas)", "price": 25000},
        "tabla 4": {"name": "Tabla de Picoteo Grande (4 personas)", "price": 25000},
        "tabla 4 personas": {"name": "Tabla de Picoteo Grande (4 personas)", "price": 25000},
        "tabla pequena": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "tabla pequeña": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "tabla de picoteo pequeña": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "tabla de picoteo pequena": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "tabla 2": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "tabla 2 personas": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "picoteo": {"name": "Tabla de Picoteo Grande (4 personas)", "price": 25000},
        "picoteo grande": {"name": "Tabla de Picoteo Grande (4 personas)", "price": 25000},
        "picoteo pequeño": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "picoteo pequeno": {"name": "Tabla de Picoteo Pequeña (2 personas)", "price": 20000},
        "tabla": {"name": "Tabla de Picoteo Grande (4 personas)", "price": 25000},  # Default a grande
        "tablas": {"name": "Tabla de Picoteo Grande (4 personas)", "price": 25000},  # Plural default a grande
        
        # Bebidas y Jugos (sin alcohol)
        "jugo": {"name": "Jugo Natural 1L", "price": 10000},
        "jugo natural": {"name": "Jugo Natural 1L", "price": 10000},
        "jugo 1l": {"name": "Jugo Natural 1L", "price": 10000},
        "jugos": {"name": "Jugo Natural 1L", "price": 10000},
        "jugos naturales": {"name": "Jugo Natural 1L", "price": 10000},
        "piña": {"name": "Jugo Natural 1L", "price": 10000},
        "pina": {"name": "Jugo Natural 1L", "price": 10000},
        "naranja": {"name": "Jugo Natural 1L", "price": 10000},
        "bebida": {"name": "Lata Bebida (Coca-Cola o Fanta)", "price": 2900},
        "lata": {"name": "Lata Bebida (Coca-Cola o Fanta)", "price": 2900},
        "coca": {"name": "Lata Bebida (Coca-Cola o Fanta)", "price": 2900},
        "coca cola": {"name": "Lata Bebida (Coca-Cola o Fanta)", "price": 2900},
        "fanta": {"name": "Lata Bebida (Coca-Cola o Fanta)", "price": 2900},
        "gaseosa": {"name": "Lata Bebida (Coca-Cola o Fanta)", "price": 2900},
        "agua": {"name": "Agua Mineral 1.5L", "price": 2500},
        "agua mineral": {"name": "Agua Mineral 1.5L", "price": 2500},
        
        # Helados (sin especificar sabor - se preguntará después)
        "helado": {"name": "Helado Individual", "price": 3500},
        "helados": {"name": "Helado Individual", "price": 3500},
        
        # Helados con sabor específico
        "helado cookies": {"name": "Helado Individual (Cookies & Cream)", "price": 3500},
        "helado cookies cream": {"name": "Helado Individual (Cookies & Cream)", "price": 3500},
        "helado cookies & cream": {"name": "Helado Individual (Cookies & Cream)", "price": 3500},
        "cookies cream": {"name": "Helado Individual (Cookies & Cream)", "price": 3500},
        "cookies & cream": {"name": "Helado Individual (Cookies & Cream)", "price": 3500},
        "helado frambuesa": {"name": "Helado Individual (Frambuesa con Chocolate Belga)", "price": 3500},
        "helado chocolate": {"name": "Helado Individual (Frambuesa con Chocolate Belga)", "price": 3500},
        "frambuesa": {"name": "Helado Individual (Frambuesa con Chocolate Belga)", "price": 3500},
        "frambuesa chocolate": {"name": "Helado Individual (Frambuesa con Chocolate Belga)", "price": 3500},
        
        # Modo Romántico
        "modo romantico": {"name": "Modo Romántico", "price": 25000},
        "modo romántico": {"name": "Modo Romántico", "price": 25000},
        "romantico": {"name": "Modo Romántico", "price": 25000},
        "romántico": {"name": "Modo Romántico", "price": 25000},
        "petalo": {"name": "Modo Romántico", "price": 25000},
        "petalos": {"name": "Modo Romántico", "price": 25000},
        "pétalos": {"name": "Modo Romántico", "price": 25000},
        "rosas": {"name": "Modo Romántico", "price": 25000},
        "rosa": {"name": "Modo Romántico", "price": 25000},
        
        # Decoración Nocturna Extra
        "velas": {"name": "Velas LED Decorativas", "price": 10000},
        "velas led": {"name": "Velas LED Decorativas", "price": 10000},
        "letras": {"name": "Letras Luminosas 'Te Amo' / 'Love'", "price": 15000},
        "letras luminosas": {"name": "Letras Luminosas 'Te Amo' / 'Love'", "price": 15000},
        "te amo": {"name": "Letras Luminosas 'Te Amo' / 'Love'", "price": 15000},
        "love": {"name": "Letras Luminosas 'Te Amo' / 'Love'", "price": 15000},
        "pack nocturno": {"name": "Pack Nocturno Completo (velas + letras)", "price": 20000},
        "pack completo": {"name": "Pack Nocturno Completo (velas + letras)", "price": 20000},
        "pack de noche": {"name": "Pack Nocturno Completo (velas + letras)", "price": 20000},
        
        # Video personalizado
        "video 15": {"name": "Video Personalizado 15s", "price": 30000},
        "video 15s": {"name": "Video Personalizado 15s", "price": 30000},
        "video corto": {"name": "Video Personalizado 15s", "price": 30000},
        "video 60": {"name": "Video Personalizado 60s", "price": 40000},
        "video 60s": {"name": "Video Personalizado 60s", "price": 40000},
        "video largo": {"name": "Video Personalizado 60s", "price": 40000},
        "video": {"name": "Video Personalizado 15s", "price": 30000},  # Default a 15s
        "video personalizado": {"name": "Video Personalizado 15s", "price": 30000},
        
        # Transporte
        "transporte": {"name": "Transporte Ida y Vuelta desde Pucón", "price": 50000},
        "transporte pucon": {"name": "Transporte Ida y Vuelta desde Pucón", "price": 50000},
        "transporte pucón": {"name": "Transporte Ida y Vuelta desde Pucón", "price": 50000},
        "ida vuelta": {"name": "Transporte Ida y Vuelta desde Pucón", "price": 50000},
        "ida y vuelta": {"name": "Transporte Ida y Vuelta desde Pucón", "price": 50000},
        
        # Toallas
        "toalla normal": {"name": "Toalla Normal", "price": 9000},
        "toalla poncho": {"name": "Toalla Poncho", "price": 10000},
        "toallas poncho": {"name": "Toalla Poncho", "price": 10000},  # Plural
        "toallas normal": {"name": "Toalla Normal", "price": 9000},  # Plural
        "toalla": {"name": "Toalla Normal", "price": 9000},  # Default a normal
        "toallas": {"name": "Toalla Normal", "price": 9000},  # Plural default a normal
        "poncho": {"name": "Toalla Poncho", "price": 10000},
        "ponchos": {"name": "Toalla Poncho", "price": 10000},
        
        # Chalas de ducha
        "chalas": {"name": "Chalas de Ducha", "price": 10000},
        "chalas de ducha": {"name": "Chalas de Ducha", "price": 10000},
        "sandalias": {"name": "Chalas de Ducha", "price": 10000},
        
        # Reserva FLEX
        "reserva flex": {"name": "Reserva FLEX (+10%)", "price": 0},  # Se calcula como % del total
        "flex": {"name": "Reserva FLEX (+10%)", "price": 0},
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
            # Remove any existing reservation AND any existing FLEX (since FLEX is tied to reservation)
            cart = [i for i in cart if i.item_type != "reservation" and i.name != "Reserva FLEX (+10%)"]
        
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
                    # FLEX is calculated as 10% of ONLY the reservation cost (passengers)
                    # NOT including other extras
                    reservation_total = sum(i.price * i.quantity for i in items if i.item_type == "reservation")
                    total += int(reservation_total * 0.1)
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
        
        # Calculate FLEX if present (10% of ONLY reservation cost, not extras)
        if any(item.name == "Reserva FLEX (+10%)" for item in items):
            reservation_cost = sum(i.price * i.quantity for i in items if i.item_type == "reservation")
            flex_amount = int(reservation_cost * 0.1)
            total += flex_amount
            message = message.replace(
                "🔒 Reserva FLEX (+10%)\n   (Se aplica al subtotal)\n\n",
                f"🔒 Reserva FLEX (+10%)\n   ${flex_amount:,}\n   (10% del costo de pasajeros)\n\n"
            )
        
        message += f"━━━━━━━━━━━━━━━━\n"
        message += f"💰 *Total: ${total:,}*"
        
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

