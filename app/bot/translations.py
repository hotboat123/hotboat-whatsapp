"""
Multi-language support for HotBoat WhatsApp Bot
Supports: Spanish (default), English, Portuguese
"""

LANGUAGES = {
    "es": "Español 🇨🇱",
    "en": "English 🇺🇸",
    "pt": "Português 🇧🇷"
}

TRANSLATIONS = {
    # Welcome and Language Selection
    "welcome_with_language": {
        "es": """🥬 ¡Ahoy! ⚓

Soy *Popeye el Marino*, cabo segundo del *HotBoat Chile* 🚤

Antes de zarpar, elige tu idioma / Choose your language / Escolha seu idioma:

1️⃣ Español 🇨🇱
2️⃣ English 🇺🇸
3️⃣ Português 🇧🇷

Escribe el número de tu idioma / Type your language number / Digite o número do seu idioma""",
        "en": """🥬 Ahoy! ⚓

I'm *Popeye the Sailor*, second mate of *HotBoat Chile* 🚤

Before we set sail, choose your language:

1️⃣ Español 🇨🇱
2️⃣ English 🇺🇸
3️⃣ Português 🇧🇷

Type your language number""",
        "pt": """🥬 Ahoy! ⚓

Eu sou *Popeye o Marinheiro*, segundo imediato do *HotBoat Chile* 🚤

Antes de zarpar, escolha seu idioma:

1️⃣ Español 🇨🇱
2️⃣ English 🇺🇸
3️⃣ Português 🇧🇷

Digite o número do seu idioma"""
    },
    
    # Main Menu
    "main_menu": {
        "es": """🥬 ¡Ahoy, grumete! ⚓

Soy *Popeye el Marino*, cabo segundo del *HotBoat Chile* 🚤

Estoy al mando para ayudarte con todas tus consultas sobre nuestras experiencias flotantes 🌊

Puedes preguntarme por:

1️⃣ *Disponibilidad y horarios*

2️⃣ *Precios por persona*

3️⃣ *Características del HotBoat*

4️⃣ *Extras y promociones*

5️⃣ *Ubicación y reseñas*

Si prefieres hablar con el *Capitán Tomás*, escribe *Llamar a Tomás*, *Ayuda*, o simplemente *6️⃣* 👨‍✈️🌿

¿Listo para zarpar o qué número eliges, grumete?""",
        
        "en": """🥬 Ahoy, sailor! ⚓

I'm *Popeye the Sailor*, second mate of *HotBoat Chile* 🚤

I'm here to help you with all your questions about our floating experiences 🌊

You can ask me about:

1️⃣ *Availability and schedules*

2️⃣ *Prices per person*

3️⃣ *HotBoat features*

4️⃣ *Extras and promotions*

5️⃣ *Location and reviews*

If you prefer to talk to *Captain Tomás*, write *Call Tomás*, *Help*, or simply *6️⃣* 👨‍✈️🌿

Ready to set sail or what number do you choose, sailor?""",
        
        "pt": """🥬 Ahoy, marujo! ⚓

Eu sou *Popeye o Marinheiro*, segundo imediato do *HotBoat Chile* 🚤

Estou no comando para ajudá-lo com todas as suas dúvidas sobre nossas experiências flutuantes 🌊

Você pode me perguntar sobre:

1️⃣ *Disponibilidade e horários*

2️⃣ *Preços por pessoa*

3️⃣ *Características do HotBoat*

4️⃣ *Extras e promoções*

5️⃣ *Localização e avaliações*

Se preferir falar com o *Capitão Tomás*, escreva *Ligar para Tomás*, *Ajuda*, ou simplesmente *6️⃣* 👨‍✈️🌿

Pronto para zarpar ou que número você escolhe, marujo?"""
    },
    
    # Language Changed Confirmation
    "language_changed": {
        "es": "✅ Perfecto, grumete. Continuaremos en español 🇨🇱",
        "en": "✅ Perfect, sailor. We'll continue in English 🇺🇸",
        "pt": "✅ Perfeito, marujo. Continuaremos em português 🇧🇷"
    },
    
    # Language Menu Option
    "change_language": {
        "es": "🌍 *Cambiar idioma*\n\nElige tu idioma:\n1️⃣ Español 🇨🇱\n2️⃣ English 🇺🇸\n3️⃣ Português 🇧🇷",
        "en": "🌍 *Change language*\n\nChoose your language:\n1️⃣ Español 🇨🇱\n2️⃣ English 🇺🇸\n3️⃣ Português 🇧🇷",
        "pt": "🌍 *Mudar idioma*\n\nEscolha seu idioma:\n1️⃣ Español 🇨🇱\n2️⃣ English 🇺🇸\n3️⃣ Português 🇧🇷"
    },
    
    # Common Phrases
    "invalid_option": {
        "es": "⚠️ Opción no válida. Por favor, elige un número del menú.",
        "en": "⚠️ Invalid option. Please choose a number from the menu.",
        "pt": "⚠️ Opção inválida. Por favor, escolha um número do menu."
    },
    
    "help_contact_captain": {
        "es": "Para hablar directamente con el Capitán Tomás, escribe *Ayuda* o *6* 👨‍✈️",
        "en": "To talk directly to Captain Tomás, write *Help* or *6* 👨‍✈️",
        "pt": "Para falar diretamente com o Capitão Tomás, escreva *Ajuda* ou *6* 👨‍✈️"
    },
    
    # Greetings
    "greeting": {
        "es": "¡Ahoy, grumete! ⚓",
        "en": "Ahoy, sailor! ⚓",
        "pt": "Ahoy, marujo! ⚓"
    },
    
    # Menu Items Translations
    "menu_availability": {
        "es": "Disponibilidad y horarios",
        "en": "Availability and schedules",
        "pt": "Disponibilidade e horários"
    },
    
    "menu_prices": {
        "es": "Precios por persona",
        "en": "Prices per person",
        "pt": "Preços por pessoa"
    },
    
    "menu_features": {
        "es": "Características del HotBoat",
        "en": "HotBoat features",
        "pt": "Características do HotBoat"
    },
    
    "menu_extras": {
        "es": "Extras y promociones",
        "en": "Extras and promotions",
        "pt": "Extras e promoções"
    },
    
    "menu_location": {
        "es": "Ubicación y reseñas",
        "en": "Location and reviews",
        "pt": "Localização e avaliações"
    },
    
    # System Prompts for AI (context for each language)
    "ai_system_prompt_suffix": {
        "es": "\n\nIMPORTANTE: Responde en español chileno de manera natural y amigable.",
        "en": "\n\nIMPORTANT: Respond in English in a natural and friendly way.",
        "pt": "\n\nIMPORTANTE: Responda em português brasileiro de forma natural e amigável."
    },
    
    # Business Info Translations
    "business_info": {
        "es": """INFORMACIÓN DEL NEGOCIO:
- HotBoat Trip: Paseos en tina caliente flotante con motor eléctrico por la Laguna Rivera
- Ubicación: Villarrica, Chile
- Capacidad: 2 a 7 personas
- Experiencia única de relajación en la naturaleza 🌿""",
        
        "en": """BUSINESS INFORMATION:
- HotBoat Trip: Hot tub boat rides with electric motor on Laguna Rivera
- Location: Villarrica, Chile
- Capacity: 2 to 7 people
- Unique relaxation experience in nature 🌿""",
        
        "pt": """INFORMAÇÕES DO NEGÓCIO:
- HotBoat Trip: Passeios em banheira flutuante com motor elétrico na Laguna Rivera
- Localização: Villarrica, Chile
- Capacidade: 2 a 7 pessoas
- Experiência única de relaxamento na natureza 🌿"""
    },
    
    # Cart Messages
    "cart_empty": {
        "es": "🛒 Tu carrito está vacío, grumete ⚓\n\n¿Qué te gustaría agregar? 🚤",
        "en": "🛒 Your cart is empty, sailor ⚓\n\nWhat would you like to add? 🚤",
        "pt": "🛒 Seu carrinho está vazio, marujo ⚓\n\nO que você gostaria de adicionar? 🚤"
    },
    
    "cart_needs_reservation": {
        "es": "📅 Necesitas agregar una reserva primero. Consulta disponibilidad y luego agrega la fecha y horario que prefieras.",
        "en": "📅 You need to add a reservation first. Check availability and then add your preferred date and time.",
        "pt": "📅 Você precisa adicionar uma reserva primeiro. Consulte a disponibilidade e adicione a data e horário de sua preferência."
    },
    
    # Call Captain Tomás
    "contact_captain": {
        "es": "📞 El Capitán Tomás se comunicará contigo pronto para confirmar todos los detalles 👨‍✈️",
        "en": "📞 Captain Tomás will contact you soon to confirm all the details 👨‍✈️",
        "pt": "📞 O Capitão Tomás entrará em contato em breve para confirmar todos os detalhes 👨‍✈️"
    },
    
    # Global Shortcuts Info
    "shortcuts_info": {
        "es": """📝 *Atajos Globales*:
• 18 = Ver extras
• 19 = Menú principal
• 20 = Ver carrito""",
        "en": """📝 *Global Shortcuts*:
• 18 = View extras
• 19 = Main menu
• 20 = View cart""",
        "pt": """📝 *Atalhos Globais*:
• 18 = Ver extras
• 19 = Menu principal
• 20 = Ver carrinho"""
    },
    
    # Prices (same numbers, different currency format)
    "prices_info": {
        "es": """PRECIOS POR PERSONA:
- 2 personas: $69,990 por persona (Total: $139,980)
- 3 personas: $54,990 por persona (Total: $164,970)
- 4 personas: $44,990 por persona (Total: $179,960)
- 5 personas: $38,990 por persona (Total: $194,950)
- 6 personas: $32,990 por persona (Total: $197,940)
- 7 personas: $29,990 por persona (Total: $209,930)
*Niños pagan desde los 6 años""",
        
        "en": """PRICES PER PERSON:
- 2 people: $69,990 per person (Total: $139,980 CLP)
- 3 people: $54,990 per person (Total: $164,970 CLP)
- 4 people: $44,990 per person (Total: $179,960 CLP)
- 5 people: $38,990 per person (Total: $194,950 CLP)
- 6 people: $32,990 per person (Total: $197,940 CLP)
- 7 people: $29,990 per person (Total: $209,930 CLP)
*Children pay from 6 years old""",
        
        "pt": """PREÇOS POR PESSOA:
- 2 pessoas: $69.990 por pessoa (Total: $139.980 CLP)
- 3 pessoas: $54.990 por pessoa (Total: $164.970 CLP)
- 4 pessoas: $44.990 por pessoa (Total: $179.960 CLP)
- 5 pessoas: $38.990 por pessoa (Total: $194.950 CLP)
- 6 pessoas: $32.990 por pessoa (Total: $197.940 CLP)
- 7 pessoas: $29.990 por pessoa (Total: $209.930 CLP)
*Crianças pagam a partir dos 6 anos"""
    }
}


def get_text(key: str, language: str = "es") -> str:
    """
    Get translated text for a given key and language
    
    Args:
        key: Translation key
        language: Language code (es, en, pt)
    
    Returns:
        Translated text, defaults to Spanish if not found
    """
    if key not in TRANSLATIONS:
        return f"[Missing translation: {key}]"
    
    if language not in TRANSLATIONS[key]:
        language = "es"  # Default to Spanish
    
    return TRANSLATIONS[key][language]


def is_language_selection(message: str) -> bool:
    """
    Check if message is a language selection (1, 2, 3)
    
    Args:
        message: User message
    
    Returns:
        True if message is a language selection number
    """
    message = message.strip()
    return message in ["1", "2", "3"]


def get_language_from_selection(selection: str) -> str:
    """
    Convert selection number to language code
    
    Args:
        selection: "1", "2", or "3"
    
    Returns:
        Language code: "es", "en", or "pt"
    """
    mapping = {
        "1": "es",
        "2": "en",
        "3": "pt"
    }
    return mapping.get(selection, "es")


def detect_language_command(message: str) -> bool:
    """
    Check if user wants to change language
    
    Args:
        message: User message
    
    Returns:
        True if message indicates language change request
    """
    message_lower = message.lower().strip()
    language_keywords = [
        "cambiar idioma", "change language", "mudar idioma",
        "idioma", "language", "língua", "lingua",
        "español", "english", "português", "portugues",
        "🌍"
    ]
    
    return any(keyword in message_lower for keyword in language_keywords)

