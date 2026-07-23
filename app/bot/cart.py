"""
Shopping Cart Manager - handles cart operations for reservations and extras
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass, asdict
import json

from app.db.connection import get_connection

# Chilean timezone
CHILE_TZ = ZoneInfo("America/Santiago")

logger = logging.getLogger(__name__)

_CART_LABELS = {
    "es": {
        "title": "🛒 *Tu Carrito HotBoat*",
        "empty": "🛒 Tu carrito está vacío, grumete ⚓\n\nEscribe *agregar* seguido del extra o servicio que quieras.",
        "reservation": "📅 *Reserva HotBoat*",
        "date": "Fecha",
        "time": "Horario",
        "people": "Personas",
        "price": "Precio",
        "subtotal": "Subtotal",
        "checkin": "Check-in",
        "checkout": "Check-out",
        "guests": "Huéspedes",
        "nights": "Noches",
        "flex_subtotal": "(Se aplica al subtotal)",
        "flex_percent": "(10% del costo de pasajeros)",
        "total": "💰 *Total: ${total:,}*",
        "child_discount": "Descuento niños",
    },
    "en": {
        "title": "🛒 *Your HotBoat Cart*",
        "empty": "🛒 Your cart is empty, sailor ⚓\n\nWrite *add* followed by the extra or service you want.",
        "reservation": "📅 *HotBoat Reservation*",
        "date": "Date",
        "time": "Time",
        "people": "People",
        "price": "Price",
        "subtotal": "Subtotal",
        "checkin": "Check-in",
        "checkout": "Check-out",
        "guests": "Guests",
        "nights": "Nights",
        "flex_subtotal": "(Applied to subtotal)",
        "flex_percent": "(10% of passenger cost)",
        "total": "💰 *Total: ${total:,}*",
        "child_discount": "Child discount",
    },
    "pt": {
        "title": "🛒 *Seu Carrinho HotBoat*",
        "empty": "🛒 Seu carrinho está vazio, marujo ⚓\n\nEscreva *adicionar* seguido do extra ou serviço que quiser.",
        "reservation": "📅 *Reserva HotBoat*",
        "date": "Data",
        "time": "Horário",
        "people": "Pessoas",
        "price": "Preço",
        "subtotal": "Subtotal",
        "checkin": "Check-in",
        "checkout": "Check-out",
        "guests": "Hóspedes",
        "nights": "Noites",
        "flex_subtotal": "(Aplicado ao subtotal)",
        "flex_percent": "(10% do custo dos passageiros)",
        "total": "💰 *Total: ${total:,}*",
        "child_discount": "Desconto crianças",
    },
}


@dataclass
class CartItem:
    """Represents an item in the shopping cart"""
    item_type: str  # 'reservation', 'extra', 'accommodation'
    name: str
    price: int  # Price in CLP
    quantity: int = 1
    discount: int = 0  # Flat CLP discount off price*quantity (e.g. child discount on a reservation)
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
            "discount": self.discount,
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
            discount=data.get("discount", 0),  # .get with default — old carts saved before this field existed won't have it
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

    # Live prices loaded from extras_visibility (refreshed on startup and periodically)
    _db_prices: dict = {}  # {name_lower: price}

    @classmethod
    def refresh_prices_from_db(cls):
        """Load/refresh extra prices from extras_visibility (single source of truth)."""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT LOWER(COALESCE(name, extra_name_lower)),
                               COALESCE(precio_venta, 0)
                        FROM extras_visibility
                        WHERE precio_venta IS NOT NULL AND precio_venta > 0
                    """)
                    cls._db_prices = {row[0]: row[1] for row in cur.fetchall()}
            logger.info(f"CartManager: loaded {len(cls._db_prices)} extra prices from extras_visibility")
        except Exception as e:
            logger.warning(f"CartManager: could not load prices from DB: {e}")

    def get_extra_price(self, display_name: str, fallback_price: int) -> int:
        """Get live price for an extra, preferring DB value over hardcoded."""
        if not self.__class__._db_prices:
            self.__class__.refresh_prices_from_db()
        return self.__class__._db_prices.get(display_name.lower(), fallback_price)

    # Prices per person based on capacity
    PRICES_PER_PERSON = {
        2: 76990,
        3: 59990,
        4: 48990,
        5: 42990,
        6: 36990,
        7: 33990,
    }
    # Flat CLP discount per child (0-12) — mirrors app/booking/db.py CHILD_DISCOUNT_PER_CHILD
    CHILD_DISCOUNT_PER_CHILD = 10000
    
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
                    """, (phone_number, customer_name, cart_data, datetime.now(CHILE_TZ)))
                    
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
        
        # Check if trying to add FLEX when one already exists (max 1 FLEX per reservation)
        if item.name == "Reserva FLEX (+10%)":
            has_flex = any(i.name == "Reserva FLEX (+10%)" for i in cart)
            if has_flex:
                logger.info(f"Intento de agregar FLEX duplicado prevenido para {phone_number}")
                return False  # No agregar FLEX duplicado
        
        # Check if item already exists in cart (for extras, group them by incrementing quantity)
        if item.item_type == "extra":
            existing_item = next((i for i in cart if i.name == item.name and i.item_type == "extra"), None)
            if existing_item:
                # Item already exists, increment quantity
                existing_item.quantity += item.quantity
                logger.info(f"Item {item.name} ya existe, incrementando cantidad a {existing_item.quantity}")
                return await self.save_cart(phone_number, customer_name, cart)
        
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
                # Reservation price is per person, minus the flat child discount (if any)
                total += item.price * item.quantity - item.discount
            elif item.item_type == "extra":
                if item.name == "Reserva FLEX (+10%)":
                    # FLEX is calculated as 10% of ONLY the reservation cost (passengers,
                    # already net of the child discount) — NOT including other extras
                    reservation_total = sum(i.price * i.quantity - i.discount for i in items if i.item_type == "reservation")
                    total += int(reservation_total * 0.1)
                else:
                    total += item.price * item.quantity
            else:
                total += item.price * item.quantity
        
        return total
    
    def _calculate_nights(self, checkin: str, checkout: str) -> int:
        """Calculate number of nights between two dates"""
        try:
            # Parse dates in format like "13 marzo", "18 marzo"
            from datetime import datetime
            import locale
            
            # Try to parse with Spanish month names
            months_es = {
                'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
                'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
                'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
            }
            
            # Parse checkin
            day_in, month_in = checkin.lower().split()
            checkin_date = datetime(2026, months_es.get(month_in, 1), int(day_in))
            
            # Parse checkout
            day_out, month_out = checkout.lower().split()
            checkout_date = datetime(2026, months_es.get(month_out, 1), int(day_out))
            
            # Calculate nights
            nights = (checkout_date - checkin_date).days
            return max(1, nights)  # At least 1 night
        except Exception as e:
            logger.warning(f"Error calculating nights from {checkin} to {checkout}: {e}")
            return 1  # Default to 1 night if parsing fails
    
    def format_cart_message(self, items: List[CartItem], language: str = "es") -> str:
        """Format cart as a readable message"""
        lb = _CART_LABELS.get(language) or _CART_LABELS["es"]

        if not items:
            return lb["empty"]

        message = lb["title"] + "\n\n"

        total = 0
        reservation = None

        for i, item in enumerate(items):
            if item.item_type == "reservation":
                reservation = item
                price = item.price * item.quantity - item.discount
                message += f"{lb['reservation']}\n"
                message += f"   {lb['date']}: {item.metadata.get('date', 'N/A')}\n"
                message += f"   {lb['time']}: {item.metadata.get('time', 'N/A')}\n"
                message += f"   {lb['people']}: {item.quantity}\n"
                if item.discount > 0:
                    message += f"   {lb['child_discount']}: -${item.discount:,}\n"
                message += f"   {lb['price']}: ${price:,}\n\n"
                total += price
            elif item.item_type == "experience":
                price = item.price * item.quantity
                exp_type = item.metadata.get('experience_type', '')
                icon = "🚣" if exp_type == "rafting" else "🐴" if exp_type == "horseback" else "⛵"

                message += f"{icon} *{item.name}*\n"
                if item.quantity > 1 and exp_type != "navigation":
                    message += f"   {item.quantity} x ${item.price:,}\n"
                    message += f"   {lb['subtotal']}: ${price:,}\n\n"
                else:
                    message += f"   {lb['price']}: ${price:,}\n\n"
                total += price
            elif item.item_type == "accommodation":
                checkin = item.metadata.get('checkin_date', '')
                checkout = item.metadata.get('checkout_date', '')
                nights = self._calculate_nights(checkin, checkout) if checkin and checkout else 1
                guests = item.metadata.get('guests', 1)

                is_hostal = "Hostal" in item.name

                if is_hostal:
                    price = item.price * guests * nights
                    message += f"🏠 *{item.name}*\n"
                    message += f"   {lb['checkin']}: {checkin}\n"
                    message += f"   {lb['checkout']}: {checkout}\n"
                    message += f"   {lb['guests']}: {guests}\n"
                    message += f"   {lb['nights']}: {nights}\n"
                    message += f"   ${item.price:,} x {guests} x {nights}\n"
                    message += f"   {lb['price']}: ${price:,}\n\n"
                else:
                    price = item.price * nights
                    message += f"🏠 *{item.name}*\n"
                    message += f"   {lb['checkin']}: {checkin}\n"
                    message += f"   {lb['checkout']}: {checkout}\n"
                    message += f"   {lb['guests']}: {guests}\n"
                    message += f"   {lb['nights']}: {nights}\n"
                    message += f"   ${item.price:,} x {nights}\n"
                    message += f"   {lb['price']}: ${price:,}\n\n"

                total += price
            elif item.item_type == "extra":
                price = item.price * item.quantity
                if item.name == "Reserva FLEX (+10%)":
                    message += f"🔒 {item.name}\n"
                    message += f"   {lb['flex_subtotal']}\n\n"
                else:
                    message += f"{i}. {item.name}\n"
                    message += f"   ${price:,} ({item.quantity}x ${item.price:,})\n\n"
                    total += price

        if any(item.name == "Reserva FLEX (+10%)" for item in items):
            reservation_cost = sum(i.price * i.quantity - i.discount for i in items if i.item_type == "reservation")
            flex_amount = int(reservation_cost * 0.1)
            total += flex_amount
            message = message.replace(
                f"🔒 Reserva FLEX (+10%)\n   {lb['flex_subtotal']}\n\n",
                f"🔒 Reserva FLEX (+10%)\n   ${flex_amount:,}\n   {lb['flex_percent']}\n\n"
            )

        message += "━━━━━━━━━━━━━━━━\n"
        message += lb["total"].format(total=total)

        return message
    
    def parse_extra_from_message(self, message: str) -> Optional[CartItem]:
        """Parse extra name from user message"""
        message_lower = message.lower().strip()
        
        # Remove common prefixes
        prefixes = ["agregar", "quiero", "necesito", "dame", "pon", "agrega"]
        for prefix in prefixes:
            if message_lower.startswith(prefix):
                message_lower = message_lower[len(prefix):].strip()
        
        # Try to match with catalog (use live DB price when available)
        for key, value in self.EXTRAS_CATALOG.items():
            if key in message_lower:
                live_price = self.get_extra_price(value["name"], value["price"])
                return CartItem(
                    item_type="extra",
                    name=value["name"],
                    price=live_price,
                    quantity=1
                )
        
        return None
    
    def create_reservation_item(
        self,
        date: str,
        time: str,
        capacity: int,
        service_name: str = "HotBoat Trip",
        children: int = 0
    ) -> CartItem:
        """Create a reservation cart item. `capacity` is the total headcount
        (adults+children) — it picks the price tier same as before. `children`
        (0-12 años) is separate: they count toward `capacity`/the tier, but get
        a flat CHILD_DISCOUNT_PER_CHILD taken off the total (see calculate_total/
        format_cart_message, which read `discount` off the returned CartItem)."""
        price_per_person = self.PRICES_PER_PERSON.get(capacity, 76990)
        discount = min(children * self.CHILD_DISCOUNT_PER_CHILD, price_per_person * capacity)
        adults = max(0, capacity - children)

        return CartItem(
            item_type="reservation",
            name=f"{service_name} - {capacity} personas",
            price=price_per_person,
            quantity=capacity,
            discount=discount,
            metadata={
                "date": date,
                "time": time,
                "capacity": capacity,
                "adults": adults,
                "children": children,
                "service_name": service_name
            }
        )

