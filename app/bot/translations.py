"""
Multi-language support for HotBoat WhatsApp Bot
Supports: Spanish (default), English, Portuguese
"""

from typing import Optional

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

Soy *Popeye el Marino*, cabo segundo del *HotBoat Chile* 🚤🔥

Estoy al mando para ayudarte con todas tus dudas sobre nuestras experiencias flotantes en la laguna 🌊

Puedes preguntarme por:

1️⃣ *Disponibilidad y horarios HotBoat*

2️⃣ *Precios por persona HotBoat*

3️⃣ *Características Experiencia HotBoat*

4️⃣ *Extras HotBoat (toallas, videos, tablas, etc.)*

5️⃣ *Ubicación y Reseñas HotBoat*

6️⃣ *Otras Experiencias Pucón (Rafting, cabalgatas, velerismo)*

7️⃣ *Alojamientos y Packs Pucón*

Si prefieres hablar con el *Capitán Tomás*, escribe *"Llamar a Tomás"*, *"Ayuda"*, o simplemente *8️⃣* 👨‍✈️🌿

¿Listo para zarpar, grumete? ⛵

*¿Qué número eliges?*

Si quieres cambiar de idioma, escribe:

🇧🇷 portugués
🇺🇸 inglés""",
        
        "en": """🥬 Ahoy, sailor! ⚓

I'm *Popeye the Sailor*, second mate of *HotBoat Chile* 🚤🔥

I'm here to help you with every question about our floating experiences on the lagoon 🌊

You can ask me about:

1️⃣ *HotBoat Availability and schedules*

2️⃣ *HotBoat Prices per person*

3️⃣ *HotBoat Experience Features*

4️⃣ *HotBoat Extras (towels, videos, boards, etc.)*

5️⃣ *HotBoat Location and reviews*

6️⃣ *Other Pucón Experiences (Rafting, horseback riding, sailing)*

7️⃣ *Pucón Accommodations and Packages*

If you'd rather talk to *Captain Tomás*, write *"Call Tomás"*, *"Help"*, or simply *8️⃣* 👨‍✈️🌿

Ready to set sail, sailor? ⛵

*Which number do you choose?*

If you'd like to switch languages, type:

🇪🇸 spanish
🇧🇷 portuguese""",
        
        "pt": """🥬 Ahoy, marujo! ⚓

Eu sou *Popeye o Marinheiro*, segundo imediato do *HotBoat Chile* 🚤🔥

Estou no comando para ajudar com todas as tuas dúvidas sobre nossas experiências flutuantes na lagoa 🌊

Você pode me perguntar sobre:

1️⃣ *Disponibilidade e horários HotBoat*

2️⃣ *Preços por pessoa HotBoat*

3️⃣ *Características Experiência HotBoat*

4️⃣ *Extras HotBoat (toalhas, vídeos, tábuas, etc.)*

5️⃣ *Localização e avaliações HotBoat*

6️⃣ *Outras Experiências Pucón (Rafting, cavalgadas, vela)*

7️⃣ *Hospedagens e Pacotes Pucón*

Se preferir falar com o *Capitão Tomás*, escreva *"Ligar para Tomás"*, *"Ajuda"*, ou simplesmente *8️⃣* 👨‍✈️🌿

Pronto para zarpar, marujo? ⛵

*Qual número você escolhe?*

Se quiser mudar de idioma, escreva:

🇪🇸 espanhol
🇺🇸 inglês"""
    },
    
    # Language Changed Confirmation
    "language_changed": {
        "es": "✅ Perfecto, grumete. Continuaremos en español 🇨🇱",
        "en": "✅ Perfect, sailor. We'll continue in English 🇺🇸",
        "pt": "✅ Perfeito, marujo. Continuaremos em português 🇧🇷"
    },

    "language_not_supported": {
        "es": "⚠️ Aún no tenemos soporte para ese idioma. Por ahora puedes usar español, inglés o portugués.",
        "en": "⚠️ We don't support that language yet. For now you can use Spanish, English or Portuguese.",
        "pt": "⚠️ Ainda não temos suporte para esse idioma. Por enquanto você pode usar espanhol, inglês ou português."
    },
    
    # Language Menu Option
    "change_language": {
        "es": """🌍 *Cambiar idioma*

Escribe el idioma que quieras usar:

🇨🇱 español
🇺🇸 inglés
🇧🇷 portugués""",
        "en": """🌍 *Change language*

Type the language you want to use:

🇺🇸 english
🇪🇸 spanish
🇧🇷 portuguese""",
        "pt": """🌍 *Mudar idioma*

Digite o idioma que deseja usar:

🇧🇷 português
🇪🇸 espanhol
🇺🇸 inglês"""
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
    
    "thanks_response": {
        "es": "¡De nada, grumete! ⚓ Si necesitas algo más, dime y te ayudo.",
        "en": "You're welcome, sailor! ⚓ Let me know if you need anything else.",
        "pt": "De nada, marujo! ⚓ Me avisa se precisar de mais alguma coisa."
    },
    
    # Greetings
    "greeting": {
        "es": "¡Ahoy, grumete! ⚓",
        "en": "Ahoy, sailor! ⚓",
        "pt": "Ahoy, marujo! ⚓"
    },
    
    # Menu Items Translations
    "menu_availability": {
        "es": "Disponibilidad y horarios HotBoat",
        "en": "HotBoat Availability and schedules",
        "pt": "Disponibilidade e horários HotBoat"
    },
    
    "menu_prices": {
        "es": "Precios por persona HotBoat",
        "en": "HotBoat Prices per person",
        "pt": "Preços por pessoa HotBoat"
    },
    
    "menu_features": {
        "es": "Características Experiencia HotBoat",
        "en": "HotBoat Experience Features",
        "pt": "Características Experiência HotBoat"
    },
    
    "menu_extras": {
        "es": "Extras HotBoat (toallas, videos, tablas, etc.)",
        "en": "HotBoat Extras (towels, videos, boards, etc.)",
        "pt": "Extras HotBoat (toalhas, vídeos, tábuas, etc.)"
    },
    
    "menu_location": {
        "es": "Ubicación y Reseñas HotBoat",
        "en": "HotBoat Location and reviews",
        "pt": "Localização e avaliações HotBoat"
    },
    
    "menu_experiences": {
        "es": "Otras Experiencias Pucón (Rafting, cabalgatas, velerismo)",
        "en": "Other Pucón Experiences (Rafting, horseback riding, sailing)",
        "pt": "Outras Experiências Pucón (Rafting, cavalgadas, vela)"
    },
    
    "menu_accommodations": {
        "es": "Alojamientos y Packs Pucón",
        "en": "Pucón Accommodations and Packages",
        "pt": "Hospedagens e Pacotes Pucón"
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
        "es": "📅 Necesitas agregar una reserva primero. Usa la opción 1 del menú principal para elegir fecha y horario.",
        "en": "📅 You need to add a reservation first. Use option 1 in the main menu to choose your date and time.",
        "pt": "📅 Você precisa adicionar uma reserva primeiro. Use a opção 1 do menu principal para escolher data e horário."
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
    },
    
    # ===== FAQ RESPONSES =====
    
    # Features / Características
    "features": {
        "es": """Estas son las características de la experiencia HotBoat 🚤🔥:

⚡ Motor eléctrico (silencioso y sustentable)
⏱️ Duración: 2 horas
🔥 Tú eliges la temperatura del agua (antes y durante el paseo)
🛥️ Fácil de navegar → ¡puedes manejarlo tú mismo!
🎶 Escucha tu propia música con parlante bluetooth + bolsas impermeables
🎥 Video cinematográfico de tu aventura disponible
🍹 ¡Disfruta bebestibles a bordo del HotBoat! Se mantendrán fríos en el cooler.
🧺 Opción de tablas de picoteo a bordo
🧼 Se limpia antes de cada uso, siempre impecable

¿Te gustaría reservar tu experiencia?""",
        
        "en": """Here are the features of the HotBoat experience 🚤🔥:

⚡ Electric motor (silent and sustainable)
⏱️ Duration: 2 hours
🔥 You choose the water temperature (before and during the ride)
🛥️ Easy to navigate → you can drive it yourself!
🎶 Listen to your own music with bluetooth speaker + waterproof bags
🎥 Cinematic video of your adventure available
🍹 Enjoy drinks on board the HotBoat! They'll stay cold in the cooler.
🧺 Charcuterie board option on board
🧼 Cleaned before each use, always immaculate

Would you like to book your experience?""",
        
        "pt": """Estas são as características da experiência HotBoat 🚤🔥:

⚡ Motor elétrico (silencioso e sustentável)
⏱️ Duração: 2 horas
🔥 Você escolhe a temperatura da água (antes e durante o passeio)
🛥️ Fácil de navegar → você pode dirigir você mesmo!
🎶 Ouça sua própria música com alto-falante bluetooth + bolsas impermeáveis
🎥 Vídeo cinematográfico da sua aventura disponível
🍹 Desfrute de bebidas a bordo do HotBoat! Ficarão geladas no cooler.
🧺 Opção de tábua de frios a bordo
🧼 Limpo antes de cada uso, sempre impecável

Gostaria de reservar sua experiência?"""
    },
    
    # Pricing detailed
    "pricing": {
        "es": """💰 *Precios HotBoat:*

👥 *2 personas*
• $69.990 x persona
• Total: *$139.980*

👥 *3 personas*
• $54.990 x persona
• Total: *$164.970*

👥 *4 personas*
• $44.990 x persona
• Total: *$179.960*

👥 *5 personas*
• $38.990 x persona
• Total: *$194.950*

👥 *6 personas*
• $32.990 x persona
• Total: *$197.940*

👥 *7 personas*
• $29.990 x persona
• Total: *$209.930*

_*niños pagan desde los 6 años_

Aquí puedes reservar tu horario directo 👇
https://hotboatchile.com/es/book-hotboat/""",
        
        "en": """💰 *HotBoat Prices:*

👥 *2 people*
• $69,990 per person
• Total: *$139,980 CLP*

👥 *3 people*
• $54,990 per person
• Total: *$164,970 CLP*

👥 *4 people*
• $44,990 per person
• Total: *$179,960 CLP*

👥 *5 people*
• $38,990 per person
• Total: *$194,950 CLP*

👥 *6 people*
• $32,990 per person
• Total: *$197,940 CLP*

👥 *7 people*
• $29,990 per person
• Total: *$209,930 CLP*

_*children pay from 6 years old_

Book your time slot here 👇
https://hotboatchile.com/en/book-hotboat/""",
        
        "pt": """💰 *Preços HotBoat:*

👥 *2 pessoas*
• $69.990 por pessoa
• Total: *$139.980 CLP*

👥 *3 pessoas*
• $54.990 por pessoa
• Total: *$164.970 CLP*

👥 *4 pessoas*
• $44.990 por pessoa
• Total: *$179.960 CLP*

👥 *5 pessoas*
• $38.990 por pessoa
• Total: *$194.950 CLP*

👥 *6 pessoas*
• $32.990 por pessoa
• Total: *$197.940 CLP*

👥 *7 pessoas*
• $29.990 por pessoa
• Total: *$209.930 CLP*

_*crianças pagam a partir dos 6 anos_

Reserve seu horário aqui 👇
https://hotboatchile.com/pt/book-hotboat/"""
    },
    
    # Location
    "location": {
        "es": """📍 *Ubicación HotBoat:*

📍 Estamos entre Pucón y Curarrehue, en pleno corazón de La Araucanía 🌿

🗺️ Mira fotos, ubicación y más de 100 reseñas ⭐⭐⭐⭐⭐ de nuestros navegantes que vivieron la experiencia HotBoat!
https://maps.app.goo.gl/jVYVHRzekkmFRjEH7

🚗 Fácil acceso 100% pavimentado desde:
• Pucón: 25 min
• Villarrica centro: 50 min
• Temuco: 2 horas

¿Te gustaría reservar tu experiencia?""",
        
        "en": """📍 *HotBoat Location:*

📍 We're between Pucón and Curarrehue, in the heart of La Araucanía 🌿

🗺️ Check out photos, location and over 100 ⭐⭐⭐⭐⭐ reviews from our sailors who lived the HotBoat experience!
https://maps.app.goo.gl/jVYVHRzekkmFRjEH7

🚗 Easy access, 100% paved from:
• Pucón: 25 min
• Villarrica downtown: 50 min
• Temuco: 2 hours

Would you like to book your experience?""",
        
        "pt": """📍 *Localização HotBoat:*

📍 Estamos entre Pucón e Curarrehue, no coração de La Araucanía 🌿

🗺️ Veja fotos, localização e mais de 100 avaliações ⭐⭐⭐⭐⭐ dos nossos marinheiros que viveram a experiência HotBoat!
https://maps.app.goo.gl/jVYVHRzekkmFRjEH7

🚗 Acesso fácil, 100% pavimentado desde:
• Pucón: 25 min
• Villarrica centro: 50 min
• Temuco: 2 horas

Gostaria de reservar sua experiência?"""
    },
    
    # Extras menu
    "extras_menu": {
        "es": """✨ *Extras HotBoat:*

¿Quieres agregar algo especial a tu HotBoat?

🍇 *Tablas de Picoteo*
1️⃣ Tabla grande (4 personas) - $25.000
2️⃣ Tabla pequeña (2 personas) - $20.000

🥤 *Bebidas y Jugos* (sin alcohol)
3️⃣ Jugo natural 1L (piña o naranja) - $10.000
4️⃣ Lata bebida (Coca-Cola o Fanta) - $2.900
5️⃣ Agua mineral 1,5 L - $2.500
6️⃣ Helado individual (Cookies & Cream 🍪 o Frambuesa 🍫) - $3.500

🌹 *Modo Romántico*
7️⃣ Pétalos de rosas y decoración especial - $25.000

🌙 *Decoración Nocturna Extra*
8️⃣ Velas LED decorativas - $10.000
9️⃣ Letras luminosas "Te Amo" / "Love" - $15.000
🔟 Pack completo (velas + letras) - $20.000

✨🎥 *Video personalizado*
1️⃣1️⃣ Video 15s - $30.000
1️⃣2️⃣ Video 60s - $40.000

🚐 *Transporte*
1️⃣3️⃣ Ida y vuelta desde Pucón - $50.000

🧻 *Toallas*
1️⃣4️⃣ Toalla normal - $9.000
1️⃣5️⃣ Toalla poncho - $10.000

🩴 *Otros*
1️⃣6️⃣ Chalas de ducha - $10.000
1️⃣7️⃣ Reserva FLEX (+10% - cancela/reprograma cuando quieras)

📝 *Escribe el número del extra que deseas agregar* 🚤""",
        
        "en": """✨ *HotBoat Extras:*

Want to add something special to your HotBoat?

🍇 *Charcuterie Boards*
1️⃣ Large board (4 people) - $25,000 CLP
2️⃣ Small board (2 people) - $20,000 CLP

🥤 *Drinks and Juices* (non-alcoholic)
3️⃣ Natural juice 1L (pineapple or orange) - $10,000 CLP
4️⃣ Canned drink (Coca-Cola or Fanta) - $2,900 CLP
5️⃣ Mineral water 1.5 L - $2,500 CLP
6️⃣ Individual ice cream (Cookies & Cream 🍪 or Raspberry 🍫) - $3,500 CLP

🌹 *Romantic Mode*
7️⃣ Rose petals and special decoration - $25,000 CLP

🌙 *Extra Night Decoration*
8️⃣ Decorative LED candles - $10,000 CLP
9️⃣ Illuminated letters "Te Amo" / "Love" - $15,000 CLP
🔟 Complete pack (candles + letters) - $20,000 CLP

✨🎥 *Personalized video*
1️⃣1️⃣ 15s video - $30,000 CLP
1️⃣2️⃣ 60s video - $40,000 CLP

🚐 *Transportation*
1️⃣3️⃣ Round trip from Pucón - $50,000 CLP

🧻 *Towels*
1️⃣4️⃣ Regular towel - $9,000 CLP
1️⃣5️⃣ Poncho towel - $10,000 CLP

🩴 *Other*
1️⃣6️⃣ Shower flip-flops - $10,000 CLP
1️⃣7️⃣ FLEX Reservation (+10% - cancel/reschedule anytime)

📝 *Type the number of the extra you want to add* 🚤""",
        
        "pt": """✨ *Extras HotBoat:*

Quer adicionar algo especial ao seu HotBoat?

🍇 *Tábuas de Frios*
1️⃣ Tábua grande (4 pessoas) - $25.000 CLP
2️⃣ Tábua pequena (2 pessoas) - $20.000 CLP

🥤 *Bebidas e Sucos* (sem álcool)
3️⃣ Suco natural 1L (abacaxi ou laranja) - $10.000 CLP
4️⃣ Lata de bebida (Coca-Cola ou Fanta) - $2.900 CLP
5️⃣ Água mineral 1,5 L - $2.500 CLP
6️⃣ Sorvete individual (Cookies & Cream 🍪 ou Framboesa 🍫) - $3.500 CLP

🌹 *Modo Romântico*
7️⃣ Pétalas de rosas e decoração especial - $25.000 CLP

🌙 *Decoração Noturna Extra*
8️⃣ Velas LED decorativas - $10.000 CLP
9️⃣ Letras iluminadas "Te Amo" / "Love" - $15.000 CLP
🔟 Pacote completo (velas + letras) - $20.000 CLP

✨🎥 *Vídeo personalizado*
1️⃣1️⃣ Vídeo 15s - $30.000 CLP
1️⃣2️⃣ Vídeo 60s - $40.000 CLP

🚐 *Transporte*
1️⃣3️⃣ Ida e volta desde Pucón - $50.000 CLP

🧻 *Toalhas*
1️⃣4️⃣ Toalha normal - $9.000 CLP
1️⃣5️⃣ Toalha poncho - $10.000 CLP

🩴 *Outros*
1️⃣6️⃣ Chinelos de banho - $10.000 CLP
1️⃣7️⃣ Reserva FLEX (+10% - cancele/reagende quando quiser)

📝 *Digite o número do extra que deseja adicionar* 🚤"""
    },
    
    # Contact Captain
    "call_captain": {
        "es": """👨‍✈️🌿 *Capitán Tomás al rescate*
            
¡Perfecto, grumete! He avisado al Capitán Tomás que necesita hablar contigo 👨‍✈️
            
El Capitán tomará el timón en cuanto vuelva a cubierta y se comunicará contigo pronto 📞
            
Mientras tanto, si tienes alguna consulta urgente, puedes escribirme y trataré de ayudarte lo mejor que pueda ⚓
            
¡Gracias por tu paciencia!""",
        
        "en": """👨‍✈️🌿 *Captain Tomás to the rescue*
            
Perfect, sailor! I've notified Captain Tomás that you need to talk to him 👨‍✈️
            
The Captain will take the helm as soon as he's back on deck and will contact you soon 📞
            
In the meantime, if you have any urgent questions, you can write to me and I'll try to help you as best I can ⚓
            
Thanks for your patience!""",
        
        "pt": """👨‍✈️🌿 *Capitão Tomás ao resgate*
            
Perfeito, marujo! Avisei o Capitão Tomás que você precisa falar com ele 👨‍✈️
            
O Capitão assumirá o leme assim que retornar ao convés e entrará em contato em breve 📞
            
Enquanto isso, se você tiver alguma dúvida urgente, pode me escrever e tentarei ajudá-lo da melhor forma possível ⚓
            
Obrigado pela sua paciência!"""
    },
    
    # Duration
    "duration": {
        "es": """⏱️ *Duración del tour:*

El tour Hot Boat tiene una duración aproximada de:
• 1.5 a 2 horas en el lago

Incluye:
• Briefing de seguridad
• Recorrido por puntos destacados
• Tiempo para fotos
• Experiencia completa

¿Alguna otra duda?""",
        
        "en": """⏱️ *Tour duration:*

The Hot Boat tour lasts approximately:
• 1.5 to 2 hours on the lake

Includes:
• Safety briefing
• Tour of highlights
• Time for photos
• Complete experience

Any other questions?""",
        
        "pt": """⏱️ *Duração do passeio:*

O passeio Hot Boat tem duração aproximada de:
• 1,5 a 2 horas no lago

Inclui:
• Briefing de segurança
• Passeio pelos pontos destacados
• Tempo para fotos
• Experiência completa

Alguma outra dúvida?"""
    },
    
    # What to bring
    "what_to_bring": {
        "es": """🎒 *¿Qué traer?*

📋 Recomendamos:
• Protector solar ☀️
• Lentes de sol 🕶️
• Ropa cómoda
• Chaqueta (puede hacer viento)
• Cámara para fotos 📸
• Ganas de pasarlo bien 🎉

✅ Nosotros proporcionamos:
• Chalecos salvavidas
• Equipo de seguridad
• Guía experto

¿Lista para la aventura?""",
        
        "en": """🎒 *What to bring?*

📋 We recommend:
• Sunscreen ☀️
• Sunglasses 🕶️
• Comfortable clothes
• Jacket (it can be windy)
• Camera for photos 📸
• Ready to have fun 🎉

✅ We provide:
• Life jackets
• Safety equipment
• Expert guide

Ready for the adventure?""",
        
        "pt": """🎒 *O que trazer?*

📋 Recomendamos:
• Protetor solar ☀️
• Óculos de sol 🕶️
• Roupa confortável
• Jaqueta (pode ventar)
• Câmera para fotos 📸
• Vontade de se divertir 🎉

✅ Nós fornecemos:
• Coletes salva-vidas
• Equipamento de segurança
• Guia especializado

Pronto para a aventura?"""
    },
    
    # Weather/Season
    "weather": {
        "es": """🌤️ *Mejor época:*

Operamos principalmente en temporada alta:
• Diciembre - Marzo (verano)
• Octubre - Noviembre (primavera)

El lago Villarrica es hermoso todo el año, pero el mejor clima es en verano.

❄️ En invierno: consultar disponibilidad

¿Para qué fecha te interesa?""",
        
        "en": """🌤️ *Best season:*

We operate mainly in high season:
• December - March (summer)
• October - November (spring)

Lake Villarrica is beautiful year-round, but the best weather is in summer.

❄️ In winter: check availability

What date are you interested in?""",
        
        "pt": """🌤️ *Melhor época:*

Operamos principalmente na alta temporada:
• Dezembro - Março (verão)
• Outubro - Novembro (primavera)

O lago Villarrica é lindo o ano todo, mas o melhor clima é no verão.

❄️ No inverno: consultar disponibilidade

Para qual data você está interessado?"""
    },
    
    # Contact info
    "contact_info": {
        "es": """📞 *Contáctanos:*

📱 WhatsApp: +56 9 1234 5678
📧 Email: info@hotboatchile.com
🌐 Web: https://hotboatchile.com

📍 Villarrica, Región de La Araucanía, Chile

¡Escríbenos para reservar! 🚤""",
        
        "en": """📞 *Contact us:*

📱 WhatsApp: +56 9 1234 5678
📧 Email: info@hotboatchile.com
🌐 Web: https://hotboatchile.com

📍 Villarrica, La Araucanía Region, Chile

Write to us to book! 🚤""",
        
        "pt": """📞 *Contate-nos:*

📱 WhatsApp: +56 9 1234 5678
📧 Email: info@hotboatchile.com
🌐 Web: https://hotboatchile.com

📍 Villarrica, Região de La Araucanía, Chile

Escreva-nos para reservar! 🚤"""
    },
    
    # Cancellation policy
    "cancellation": {
        "es": """🔄 *Política de cancelación:*

• Cancelación gratuita hasta 48h antes
• Entre 24-48h: 50% de reembolso
• Menos de 24h: No reembolsable

⛈️ Mal clima: Reprogramamos sin costo

💳 Política de pago: Se requiere anticipo del 30% para reservar

¿Necesitas más información?""",
        
        "en": """🔄 *Cancellation policy:*

• Free cancellation up to 48h before
• Between 24-48h: 50% refund
• Less than 24h: Non-refundable

⛈️ Bad weather: We reschedule at no cost

💳 Payment policy: 30% deposit required to book

Need more information?""",
        
        "pt": """🔄 *Política de cancelamento:*

• Cancelamento gratuito até 48h antes
• Entre 24-48h: 50% de reembolso
• Menos de 24h: Não reembolsável

⛈️ Mau tempo: Reagendamos sem custo

💳 Política de pagamento: Depósito de 30% necessário para reservar

Precisa de mais informações?"""
    },
    
    # ===== ACCOMMODATION MESSAGES =====
    
    "accommodations_and_packages_menu": {
        "es": """🏠📦 *Alojamientos y Packs en Pucón*

¡Perfecto grumete! Te ofrezco varias opciones:

1️⃣ *Packs Completos* 🎁
   Experiencias todo incluido con alojamiento y actividades

2️⃣ *Solo Alojamientos* 🏠
   Buscar y reservar alojamiento en Pucón

3️⃣ *Arma tu Pack* 🛒
   Personaliza: elige actividades y agrega alojamiento

📲 Escribe el número que prefieras (1, 2, o 3)

💡 *Recuerda:* Escribe *"Menu"* en cualquier momento para volver al *Menú HotBoat* principal 🚤""",
        
        "en": """🏠📦 *Accommodations and Packages in Pucón*

Perfect sailor! I offer you several options:

1️⃣ *Complete Packages* 🎁
   All-inclusive experiences with accommodation and activities

2️⃣ *Accommodations Only* 🏠
   Search and book accommodation in Pucón

3️⃣ *Build Your Package* 🛒
   Customize: choose activities and add accommodation

📲 Type the number you prefer (1, 2, or 3)

💡 *Remember:* Type *"Menu"* anytime to return to the main *HotBoat Menu* 🚤""",
        
        "pt": """🏠📦 *Acomodações e Pacotes em Pucón*

Perfeito marinheiro! Ofereço várias opções:

1️⃣ *Pacotes Completos* 🎁
   Experiências tudo incluído com acomodação e atividades

2️⃣ *Apenas Acomodações* 🏠
   Buscar e reservar acomodação em Pucón

3️⃣ *Monte seu Pacote* 🛒
   Personalize: escolha atividades e adicione acomodação

📲 Digite o número que preferir (1, 2, ou 3)

💡 *Lembre-se:* Digite *"Menu"* a qualquer momento para voltar ao *Menu HotBoat* principal 🚤"""
    },
    
    "accommodations_only_intro": {
        "es": """🏠 *Alojamientos en Pucón*

Te envío imágenes con toda la información detallada de nuestros alojamientos recomendados ⬇️

📸 Después de revisar las imágenes, respóndeme:

*¿Qué alojamiento te interesa?*

1️⃣ *Open Sky* - Domos románticos con vista a las estrellas 🌌
2️⃣ *Raíces de Relikura* - Cabañas y hostal junto al río 🌿

Escribe *1* o *2*, o el nombre del alojamiento 👍

💡 *Tip:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """🏠 *Accommodations in Pucón*

I'm sending you images with all the detailed information about our recommended accommodations ⬇️

📸 After reviewing the images, tell me:

*Which accommodation interests you?*

1️⃣ *Open Sky* - Romantic domes with starry views 🌌
2️⃣ *Raíces de Relikura* - Cabins and hostel by the river 🌿

Type *1* or *2*, or the accommodation name 👍

💡 *Tip:* Type *"Menu"* to return to the *HotBoat Menu* 🚤""",
        
        "pt": """🏠 *Acomodações em Pucón*

Estou enviando imagens com todas as informações detalhadas sobre nossas acomodações recomendadas ⬇️

📸 Depois de revisar as imagens, me diga:

*Qual acomodação te interessa?*

1️⃣ *Open Sky* - Domos românticos com vista para as estrelas 🌌
2️⃣ *Raíces de Relikura* - Cabanas e albergue à beira do rio 🌿

Digite *1* ou *2*, ou o nome da acomodação 👍

💡 *Dica:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
    },
    
    "accommodations_open_sky_rooms": {
        "es": """⭐ *Open Sky - Domos Románticos*

Perfecto! Tenemos dos opciones de domos transparentes:

1️⃣ *Domo con Tina de Baño* 🛁
   💰 $100.000 / noche
   👥 2 personas (máximo 3)

2️⃣ *Domo con Hidromasaje* 💆
   💰 $120.000 / noche
   👥 2 personas (máximo 3)

¿Cuál prefieres? Escribe *1* o *2* 🌟""",
        
        "en": """⭐ *Open Sky - Romantic Domes*

Perfect! We have two transparent dome options:

1️⃣ *Dome with Bathtub* 🛁
   💰 $100,000 CLP / night
   👥 2 people (max 3)

2️⃣ *Dome with Hydromassage* 💆
   💰 $120,000 CLP / night
   👥 2 people (max 3)

Which do you prefer? Type *1* or *2* 🌟""",
        
        "pt": """⭐ *Open Sky - Domos Românticos*

Perfeito! Temos duas opções de domos transparentes:

1️⃣ *Domo com Banheira* 🛁
   💰 $100.000 CLP / noite
   👥 2 pessoas (máximo 3)

2️⃣ *Domo com Hidromassagem* 💆
   💰 $120.000 CLP / noite
   👥 2 pessoas (máximo 3)

Qual você prefere? Digite *1* ou *2* 🌟"""
    },
    
    "accommodations_relikura_rooms": {
        "es": """🌿 *Raíces de Relikura - Junto al Río*

Excelente elección! Tenemos varias opciones:

1️⃣ *Cabaña para 2 personas*
   💰 $60.000 / noche

2️⃣ *Cabaña para 4 personas*
   💰 $80.000 / noche

3️⃣ *Cabaña para 6 personas*
   💰 $100.000 / noche

4️⃣ *Hostal* (por persona)
   💰 $20.000 / noche

¿Qué opción prefieres? Escribe el número 🏡""",
        
        "en": """🌿 *Raíces de Relikura - By the River*

Excellent choice! We have several options:

1️⃣ *Cabin for 2 people*
   💰 $60,000 CLP / night

2️⃣ *Cabin for 4 people*
   💰 $80,000 CLP / night

3️⃣ *Cabin for 6 people*
   💰 $100,000 CLP / night

4️⃣ *Hostel* (per person)
   💰 $20,000 CLP / night

Which option do you prefer? Type the number 🏡""",
        
        "pt": """🌿 *Raíces de Relikura - À Beira do Rio*

Excelente escolha! Temos várias opções:

1️⃣ *Cabana para 2 pessoas*
   💰 $60.000 CLP / noite

2️⃣ *Cabana para 4 pessoas*
   💰 $80.000 CLP / noite

3️⃣ *Cabana para 6 pessoas*
   💰 $100.000 CLP / noite

4️⃣ *Albergue* (por pessoa)
   💰 $20.000 CLP / noite

Qual opção você prefere? Digite o número 🏡"""
    },
    
    "accommodations_ask_guests": {
        "es": """👥 *¿Para cuántas personas?*

Por favor indícame el número de huéspedes.

Ejemplo: *2*, *4*, *6*, etc.

📲 Escribe solo el número 👍""",
        
        "en": """👥 *For how many people?*

Please tell me the number of guests.

Example: *2*, *4*, *6*, etc.

📲 Just type the number 👍""",
        
        "pt": """👥 *Para quantas pessoas?*

Por favor me diga o número de hóspedes.

Exemplo: *2*, *4*, *6*, etc.

📲 Digite apenas o número 👍"""
    },
    
    "accommodations_ask_checkin_date": {
        "es": """📅 *¿Qué fecha tienes pensada?* (Check-in)

Por favor indícame la fecha de **entrada**.

Ejemplos válidos:
• "15 de febrero"
• "25/02/2026"
• "Febrero 15"
• "próximo sábado"

📲 Escribe la fecha de entrada 🗓️""",
        
        "en": """📅 *What date are you thinking?* (Check-in)

Please tell me your **check-in** date.

Valid examples:
• "February 15"
• "02/25/2026"
• "Feb 15"
• "next Saturday"

📲 Type the check-in date 🗓️""",
        
        "pt": """📅 *Que data você está pensando?* (Check-in)

Por favor me diga a data de **entrada**.

Exemplos válidos:
• "15 de fevereiro"
• "25/02/2026"
• "Fev 15"
• "próximo sábado"

📲 Digite a data de entrada 🗓️"""
    },
    
    "accommodations_ask_checkout_date": {
        "es": """📅 *¿En qué fecha te vas?* (Check-out)

Por favor indícame la fecha de **salida**.

Ejemplos válidos:
• "18 de febrero"
• "28/02/2026"
• "Febrero 18"
• "próximo domingo"

📲 Escribe la fecha de salida 🗓️""",
        
        "en": """📅 *What date will you leave?* (Check-out)

Please tell me your **check-out** date.

Valid examples:
• "February 18"
• "02/28/2026"
• "Feb 18"
• "next Sunday"

📲 Type the check-out date 🗓️""",
        
        "pt": """📅 *Em que data você vai embora?* (Check-out)

Por favor me diga a data de **saída**.

Exemplos válidos:
• "18 de fevereiro"
• "28/02/2026"
• "Fev 18"
• "próximo domingo"

📲 Digite a data de saída 🗓️"""
    },
    
    "accommodations_awaiting_confirmation": {
        "es": """✅ *Perfecto, grumete!*

He recibido tu solicitud de alojamiento:

📋 *Resumen:*
{summary}

⏳ Déjame verificar la disponibilidad con el establecimiento y te confirmo lo antes posible.

El *Capitán Tomás* revisará tu solicitud y te contactará para confirmar 👨‍✈️

📲 Te responderemos pronto. ¡Gracias por tu paciencia! ⚓""",
        
        "en": """✅ *Perfect, sailor!*

I've received your accommodation request:

📋 *Summary:*
{summary}

⏳ Let me check availability with the establishment and I'll confirm as soon as possible.

*Captain Tomás* will review your request and contact you to confirm 👨‍✈️

📲 We'll get back to you soon. Thanks for your patience! ⚓""",
        
        "pt": """✅ *Perfeito, marujo!*

Recebi sua solicitação de acomodação:

📋 *Resumo:*
{summary}

⏳ Deixa eu verificar a disponibilidade com o estabelecimento e confirmo o mais rápido possível.

O *Capitão Tomás* revisará sua solicitação e entrará em contato para confirmar 👨‍✈️

📲 Responderemos em breve. Obrigado pela paciência! ⚓"""
    },
    
    "complete_packages_menu": {
        "es": """🎁 *Packs Completos - Todo Incluido*

Elige tu pack ideal según tu tipo de viaje:

1️⃣ 💕 *Pack Romántico*
Escapada para 2 con Open Sky, HotBoat y velero

2️⃣ 👨‍👩‍👧‍👦 *Pack Familiar*
Aventura para 4 con Relikura, HotBoat, rafting y cabalgata

3️⃣ 👥 *Pack Amigos*
Experiencia grupal para 6 con Relikura, HotBoat y rafting

📸 Te enviaré la imagen con todos los detalles del pack que elijas.

*¿Qué pack prefieres?*
Escribe *1*, *2*, *3* o el nombre (*Romántico*, *Familiar*, *Amigos*) 🎒

💡 *Tip:* Cada pack tiene versión básica y premium. Te preguntaré después 😉

💡 *Recuerda:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """🎁 *Complete Packages - All Inclusive*

Choose your ideal package according to your trip type:

1️⃣ 💕 *Romantic Package*
Getaway for 2 with Open Sky, HotBoat and sailboat

2️⃣ 👨‍👩‍👧‍👦 *Family Package*
Adventure for 4 with Relikura, HotBoat, rafting and horseback riding

3️⃣ 👥 *Friends Package*
Group experience for 6 with Relikura, HotBoat and rafting

📸 I'll send you the image with all the details of your chosen package.

*What package do you prefer?*
Type *1*, *2*, *3* or the name (*Romantic*, *Family*, *Friends*) 🎒

💡 *Tip:* Each package has basic and premium versions. I'll ask you later 😉

💡 *Remember:* Type *"Menu"* to return to the *HotBoat Menu* 🚤""",
        
        "pt": """🎁 *Pacotes Completos - Tudo Incluído*

Escolha seu pacote ideal de acordo com seu tipo de viagem:

1️⃣ 💕 *Pacote Romântico*
Escapada para 2 com Open Sky, HotBoat e veleiro

2️⃣ 👨‍👩‍👧‍👦 *Pacote Familiar*
Aventura para 4 com Relikura, HotBoat, rafting e cavalgada

3️⃣ 👥 *Pacote Amigos*
Experiência em grupo para 6 com Relikura, HotBoat e rafting

📸 Enviarei a imagem com todos os detalhes do pacote escolhido.

*Que pacote você prefere?*
Digite *1*, *2*, *3* ou o nome (*Romântico*, *Familiar*, *Amigos*) 🎒

💡 *Dica:* Cada pacote tem versão básica e premium. Perguntarei depois 😉

💡 *Lembre-se:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
    },
    
    "build_your_package_intro": {
        "es": """🛒 *Arma tu Pack Personalizado*

¡Perfecto! Puedes elegir las actividades que quieras y luego agregar alojamiento.

📋 *Actividades Disponibles:*

1️⃣ 🚤 *HotBoat* - Experiencia flotante única
2️⃣ 🚣 *Rafting* - Adrenalina en el río
3️⃣ 🌋 *Subida al Volcán* - Trek inolvidable
4️⃣ 🐴 *Cabalgata* - Naturaleza a caballo
5️⃣ 🚗 *Arriendo de Vehículo* - Suzuki New Baleno o similar ($50.000/día)

Puedes elegir *varias opciones*. Escribe los números que te interesan separados por comas.

Ejemplo: "1, 2, 4" para HotBoat + Rafting + Cabalgata

O escribe *"Terminar"* cuando estés listo para continuar.

💡 *Recuerda:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """🛒 *Build Your Custom Package*

Perfect! You can choose the activities you want and then add accommodation.

📋 *Available Activities:*

1️⃣ 🚤 *HotBoat* - Unique floating experience
2️⃣ 🚣 *Rafting* - River adrenaline
3️⃣ 🌋 *Volcano Climb* - Unforgettable trek
4️⃣ 🐴 *Horseback Riding* - Nature on horseback
5️⃣ 🚗 *Vehicle Rental* - Suzuki New Baleno or similar ($50,000 CLP/day)

You can choose *multiple options*. Type the numbers you're interested in separated by commas.

Example: "1, 2, 4" for HotBoat + Rafting + Horseback Riding

Or type *"Done"* when you're ready to continue.

💡 *Remember:* Type *"Menu"* to return to the *HotBoat Menu* 🚤""",
        
        "pt": """🛒 *Monte seu Pacote Personalizado*

Perfeito! Você pode escolher as atividades que quiser e depois adicionar acomodação.

📋 *Atividades Disponíveis:*

1️⃣ 🚤 *HotBoat* - Experiência flutuante única
2️⃣ 🚣 *Rafting* - Adrenalina no rio
3️⃣ 🌋 *Subida ao Vulcão* - Trekking inesquecível
4️⃣ 🐴 *Cavalgada* - Natureza a cavalo
5️⃣ 🚗 *Aluguel de Veículo* - Suzuki New Baleno ou similar ($50.000 CLP/dia)

Você pode escolher *várias opções*. Digite os números que te interessam separados por vírgulas.

Exemplo: "1, 2, 4" para HotBoat + Rafting + Cavalgada

Ou digite *"Terminar"* quando estiver pronto para continuar.

💡 *Lembre-se:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
    },
    
    "build_package_ask_accommodation": {
        "es": """✅ *Actividades Seleccionadas:*
{activities}

¿Quieres agregar *alojamiento* a tu pack? 🏠

1️⃣ Sí, agregar alojamiento
2️⃣ No, solo actividades

Escribe *1* o *2* 👍

💡 *Recuerda:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """✅ *Selected Activities:*
{activities}

Do you want to add *accommodation* to your package? 🏠

1️⃣ Yes, add accommodation
2️⃣ No, only activities

Type *1* or *2* 👍

💡 *Remember:* Type *"Menu"* to return to the *HotBoat Menu* 🚤""",
        
        "pt": """✅ *Atividades Selecionadas:*
{activities}

Quer adicionar *acomodação* ao seu pacote? 🏠

1️⃣ Sim, adicionar acomodação
2️⃣ Não, apenas atividades

Digite *1* ou *2* 👍

💡 *Lembre-se:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
    },
    
    "build_package_confirmation": {
        "es": """✅ *Pack Personalizado Recibido*

📋 *Tu Selección:*
{package_summary}

El *Capitán Tomás* revisará tu solicitud y te contactará para coordinar fechas, disponibilidad y pago 👨‍✈️⚓

📲 Te responderemos pronto para confirmar todo!

💡 *Mientras tanto*, escribe *"Menu"* para explorar más opciones del *Menú HotBoat* 🚤""",
        
        "en": """✅ *Custom Package Received*

📋 *Your Selection:*
{package_summary}

*Captain Tomás* will review your request and contact you to coordinate dates, availability and payment 👨‍✈️⚓

📲 We'll get back to you soon to confirm everything!

💡 *Meanwhile*, type *"Menu"* to explore more *HotBoat Menu* options 🚤""",
        
        "pt": """✅ *Pacote Personalizado Recebido*

📋 *Sua Seleção:*
{package_summary}

O *Capitão Tomás* revisará sua solicitação e entrará em contato para coordenar datas, disponibilidade e pagamento 👨‍✈️⚓

📲 Responderemos em breve para confirmar tudo!

💡 *Enquanto isso*, digite *"Menu"* para explorar mais opções do *Menu HotBoat* 🚤"""
    },
    
    "accommodations": {
        "es": """🌊🔥 *HotBoat + Alojamiento en Pucón*

Arma tu experiencia a tu medida con HotBoat y nuestros alojamientos recomendados.

⭐ *Open Sky* – Para parejas románticas
Domos transparentes con vista a las estrellas 🌌

💰 $100.000 / noche – Domo con tina de baño interior (2 pers.)
💰 $120.000 / noche – Domo con hidromasaje interior (2 pers.)

🌿 *Raíces de Relikura* – Familiar con actividades
Hostal y cabañas junto al río, con tinaja y entorno natural 🍃

*Cabañas:*
💰 $60.000 / noche (2 pers.)
💰 $80.000 / noche (4 pers.)
💰 $100.000 / noche (6 pers.)

*Hostal:*
💰 $20.000 / noche por persona

📌 *Cómo funciona:*
1. Me dices la fecha y la opción de alojamiento
2. Te confirmo disponibilidad
3. Pagas todo en un solo link y quedas reservado

📲 Responde este mensaje con la fecha y alojamiento que prefieras""",
        
        "en": """🌊🔥 *HotBoat + Accommodation in Pucón*

Build your experience your way with HotBoat and our recommended accommodations.

⭐ *Open Sky* – For romantic couples
Transparent domes with starry views 🌌

💰 $100,000 CLP / night – Dome with indoor bathtub (2 people)
💰 $120,000 CLP / night – Dome with indoor hydromassage (2 people)

🌿 *Raíces de Relikura* – Family with activities
Hostel and cabins by the river, with hot tub and natural surroundings 🍃

*Cabins:*
💰 $60,000 CLP / night (2 people)
💰 $80,000 CLP / night (4 people)
💰 $100,000 CLP / night (6 people)

*Hostel:*
💰 $20,000 CLP / night per person

📌 *How it works:*
1. Tell me the date and accommodation option
2. I confirm availability
3. Pay everything in one link and you're booked

📲 Reply to this message with your preferred date and accommodation""",
        
        "pt": """🌊🔥 *HotBoat + Hospedagem em Pucón*

Monte sua experiência do seu jeito com HotBoat e nossas hospedagens recomendadas.

⭐ *Open Sky* – Para casais românticos
Domos transparentes com vista para as estrelas 🌌

💰 $100.000 CLP / noite – Domo com banheira interna (2 pessoas)
💰 $120.000 CLP / noite – Domo com hidromassagem interna (2 pessoas)

🌿 *Raíces de Relikura* – Familiar com atividades
Albergue e cabanas à beira do rio, com ofurô e ambiente natural 🍃

*Cabanas:*
💰 $60.000 CLP / noite (2 pessoas)
💰 $80.000 CLP / noite (4 pessoas)
💰 $100.000 CLP / noite (6 pessoas)

*Albergue:*
💰 $20.000 CLP / noite por pessoa

📌 *Como funciona:*
1. Me diz a data e a opção de hospedagem
2. Confirmo a disponibilidade
3. Pague tudo em um link e você está reservado

📲 Responda esta mensagem com sua data e hospedagem preferidas"""
    },
    
    # ===== RESERVATION FLOW MESSAGES =====
    
    "ask_for_date": {
        "es": """📅 *¿Para qué fecha te gustaría reservar?*

Escríbeme la fecha, por ejemplo:
• "15 de enero"
• "martes 23"
• "próximo sábado"

¿Qué fecha prefieres, grumete? ⚓

━━━━━━━━━━━━━━━━━━━━━━━━
💡 *Tip:* Escribe *"menú"* si quieres volver al menú principal""",
        
        "en": """📅 *What date would you like to book?*

Write me the date, for example:
• "January 15"
• "Tuesday 23rd"
• "next Saturday"

What date do you prefer, sailor? ⚓

━━━━━━━━━━━━━━━━━━━━━━━━
💡 *Tip:* Write *"menu"* if you want to go back to the main menu""",
        
        "pt": """📅 *Para qual data você gostaria de reservar?*

Escreva-me a data, por exemplo:
• "15 de janeiro"
• "terça-feira 23"
• "próximo sábado"

Que data você prefere, marujo? ⚓

━━━━━━━━━━━━━━━━━━━━━━━━
💡 *Dica:* Escreva *"menu"* se quiser voltar ao menu principal"""
    },
    
    "ask_for_party_size": {
        "es": """👥 *¿Para cuántas personas?*

Por favor, escríbeme el número de personas (de 2 a 7):
• Ejemplo: "4 personas"
• O simplemente: "4"

¿Cuántos navegantes zarparán? ⚓""",
        
        "en": """👥 *For how many people?*

Please write me the number of people (2 to 7):
• Example: "4 people"
• Or simply: "4"

How many sailors will set sail? ⚓""",
        
        "pt": """👥 *Para quantas pessoas?*

Por favor, escreva-me o número de pessoas (de 2 a 7):
• Exemplo: "4 pessoas"
• Ou simplesmente: "4"

Quantos marinheiros vão zarpar? ⚓"""
    },
    
    "reservation_confirmed": {
        "es": """✅ *Solicitud de Reserva Recibida*

📞 *El Capitán Tomás se comunicará contigo pronto por WhatsApp o teléfono para confirmar tu reserva y coordinar el pago* 👨‍✈️

Por mientras, envíanos tu *email* y *nombre completo* por favor 📝

¡Gracias por elegir HotBoat! 🚤🌊""",
        
        "en": """✅ *Reservation Request Received*

📞 *Captain Tomás will contact you soon via WhatsApp or phone to confirm your booking and coordinate payment* 👨‍✈️

In the meantime, please send us your *email* and *full name* 📝

Thanks for choosing HotBoat! 🚤🌊""",
        
        "pt": """✅ *Solicitação de Reserva Recebida*

📞 *O Capitão Tomás entrará em contato em breve via WhatsApp ou telefone para confirmar sua reserva e coordenar o pagamento* 👨‍✈️

Enquanto isso, envie-nos seu *email* e *nome completo* por favor 📝

Obrigado por escolher HotBoat! 🚤🌊"""
    },
    
    "invalid_party_size": {
        "es": "⚠️ El número debe ser entre 2 y 7 personas. ¿Cuántos serán?",
        "en": "⚠️ The number must be between 2 and 7 people. How many will you be?",
        "pt": "⚠️ O número deve ser entre 2 e 7 pessoas. Quantos serão?"
    },
    
    "extra_added": {
        "es": "✅ Extra agregado al carrito",
        "en": "✅ Extra added to cart",
        "pt": "✅ Extra adicionado ao carrinho"
    },
    
    "cart_cleared": {
        "es": "🗑️ Carrito vaciado",
        "en": "🗑️ Cart cleared",
        "pt": "🗑️ Carrinho esvaziado"
    },
    
    "processing": {
        "es": "⏳ Procesando...",
        "en": "⏳ Processing...",
        "pt": "⏳ Processando..."
    },
    
    # ========== EXPERIENCES FLOW ==========
    
    "experiences_menu": {
        "es": """📋 *Experiencias y Actividades*

¡Explora las mejores aventuras en Pucón! 🏔️

📋 *Experiencias Disponibles:*

1️⃣ 🚣 *Rafting* - Adrenalina en el río
2️⃣ 🐴 *Cabalgata* - Naturaleza a caballo
3️⃣ ⛵ *Navegación* - Explora lagos y ríos

*¿Qué experiencia te interesa?*

Escribe el número de tu elección (1, 2 o 3)

💡 *Recuerda:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """📋 *Experiences and Activities*

Explore the best adventures in Pucón! 🏔️

📋 *Available Experiences:*

1️⃣ 🚣 *Rafting* - River adrenaline
2️⃣ 🐴 *Horseback Riding* - Nature on horseback
3️⃣ ⛵ *Navigation* - Explore lakes and rivers

*Which experience interests you?*

Type the number of your choice (1, 2 or 3)

💡 *Remember:* Type *"Menu"* to return to *HotBoat Menu* 🚤""",
        
        "pt": """📋 *Experiências e Atividades*

Explore as melhores aventuras em Pucón! 🏔️

📋 *Experiências Disponíveis:*

1️⃣ 🚣 *Rafting* - Adrenalina no rio
2️⃣ 🐴 *Cavalgada* - Natureza a cavalo
3️⃣ ⛵ *Navegação* - Explore lagos e rios

*Qual experiência te interessa?*

Digite o número da sua escolha (1, 2 ou 3)

💡 *Lembre-se:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
    },
    
    # Rafting Options
    "rafting_options": {
        "es": """🚣 *Rafting - Elige tu Nivel*

📍 Vive la adrenalina del río en Pucón

*Opciones Disponibles:*

1️⃣ *Rafting Bajo* - Nivel principiante
   💰 $30.000 por persona
   ⏱️ Duración: 2-3 horas
   🌊 Dificultad: Baja (ideal para familias)

2️⃣ *Rafting Alto* - Nivel avanzado
   💰 $40.000 por persona
   ⏱️ Duración: 3-4 horas
   🌊 Dificultad: Alta (más adrenalina)

*¿Qué nivel prefieres?*

Escribe 1 para Bajo o 2 para Alto

💡 *Recuerda:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """🚣 *Rafting - Choose Your Level*

📍 Experience the river adrenaline in Pucón

*Available Options:*

1️⃣ *Low Rafting* - Beginner level
   💰 $30,000 CLP per person
   ⏱️ Duration: 2-3 hours
   🌊 Difficulty: Low (ideal for families)

2️⃣ *High Rafting* - Advanced level
   💰 $40,000 CLP per person
   ⏱️ Duration: 3-4 hours
   🌊 Difficulty: High (more adrenaline)

*Which level do you prefer?*

Type 1 for Low or 2 for High

💡 *Remember:* Type *"Menu"* to return to *HotBoat Menu* 🚤""",
        
        "pt": """🚣 *Rafting - Escolha Seu Nível*

📍 Viva a adrenalina do rio em Pucón

*Opções Disponíveis:*

1️⃣ *Rafting Baixo* - Nível iniciante
   💰 $30.000 CLP por pessoa
   ⏱️ Duração: 2-3 horas
   🌊 Dificuldade: Baixa (ideal para famílias)

2️⃣ *Rafting Alto* - Nível avançado
   💰 $40.000 CLP por pessoa
   ⏱️ Duração: 3-4 horas
   🌊 Dificuldade: Alta (mais adrenalina)

*Qual nível você prefere?*

Digite 1 para Baixo ou 2 para Alto

💡 *Lembre-se:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
    },
    
    # Horseback Riding Options
    "horseback_options": {
        "es": """🐴 *Cabalgata - Opciones Disponibles*

📍 Explora la naturaleza a caballo

*Opciones Disponibles:*

1️⃣ *Cabalgata Parque Ojos del Caburguá*
   💰 $50.000 por persona
   ⏱️ Duración: 3-4 horas
   🌲 Incluye: Guía, equipo completo y snack

*¿Te interesa esta cabalgata?*

Escribe 1 para confirmar o "Menu" para volver

💡 *Recuerda:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """🐴 *Horseback Riding - Available Options*

📍 Explore nature on horseback

*Available Options:*

1️⃣ *Horseback Riding Ojos del Caburguá Park*
   💰 $50,000 CLP per person
   ⏱️ Duration: 3-4 hours
   🌲 Includes: Guide, complete equipment and snack

*Are you interested in this ride?*

Type 1 to confirm or "Menu" to go back

💡 *Remember:* Type *"Menu"* to return to *HotBoat Menu* 🚤""",
        
        "pt": """🐴 *Cavalgada - Opções Disponíveis*

📍 Explore a natureza a cavalo

*Opções Disponíveis:*

1️⃣ *Cavalgada Parque Ojos del Caburguá*
   💰 $50.000 CLP por pessoa
   ⏱️ Duração: 3-4 horas
   🌲 Inclui: Guia, equipamento completo e lanche

*Você está interessado nesta cavalgada?*

Digite 1 para confirmar ou "Menu" para voltar

💡 *Lembre-se:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
    },
    
    # Navigation Options
    "navigation_options": {
        "es": """⛵ *Navegación - Elige tu Experiencia*

📍 Explora lagos y ríos en embarcación

*Opciones Disponibles:*

1️⃣ *Travesía 30 minutos (2p)* - $300.000
2️⃣ *Travesía 30 minutos (4p)* - $340.000
3️⃣ *Travesía 30 minutos (6p)* - $360.000
4️⃣ *Travesía 30 minutos (8p)* - $380.000
5️⃣ *Travesía 30 minutos (10p)* - $400.000

6️⃣ *Yave a vela Akimbo 2p (1.5hr)* - $120.000
7️⃣ *Yave a vela Akimbo 3p (1.5hr)* - $130.000
8️⃣ *Yave a vela Akimbo 4p (1.5hr)* - $140.000
9️⃣ *Yave a vela Akimbo 5p (1.5hr)* - $150.000
🔟 *Yave a vela Akimbo 5p (1.5hr)* - $160.000

*¿Qué opción prefieres?*

Escribe el número de tu elección (1-10)

💡 *Recuerda:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """⛵ *Navigation - Choose Your Experience*

📍 Explore lakes and rivers by boat

*Available Options:*

1️⃣ *30-minute crossing (2p)* - $300,000 CLP
2️⃣ *30-minute crossing (4p)* - $340,000 CLP
3️⃣ *30-minute crossing (6p)* - $360,000 CLP
4️⃣ *30-minute crossing (8p)* - $380,000 CLP
5️⃣ *30-minute crossing (10p)* - $400,000 CLP

6️⃣ *Sailboat Akimbo 2p (1.5hr)* - $120,000 CLP
7️⃣ *Sailboat Akimbo 3p (1.5hr)* - $130,000 CLP
8️⃣ *Sailboat Akimbo 4p (1.5hr)* - $140,000 CLP
9️⃣ *Sailboat Akimbo 5p (1.5hr)* - $150,000 CLP
🔟 *Sailboat Akimbo 5p (1.5hr)* - $160,000 CLP

*Which option do you prefer?*

Type the number of your choice (1-10)

💡 *Remember:* Type *"Menu"* to return to *HotBoat Menu* 🚤""",
        
        "pt": """⛵ *Navegação - Escolha Sua Experiência*

📍 Explore lagos e rios de barco

*Opções Disponíveis:*

1️⃣ *Travessia 30 minutos (2p)* - $300.000 CLP
2️⃣ *Travessia 30 minutos (4p)* - $340.000 CLP
3️⃣ *Travessia 30 minutos (6p)* - $360.000 CLP
4️⃣ *Travessia 30 minutos (8p)* - $380.000 CLP
5️⃣ *Travessia 30 minutos (10p)* - $400.000 CLP

6️⃣ *Veleiro Akimbo 2p (1.5hr)* - $120.000 CLP
7️⃣ *Veleiro Akimbo 3p (1.5hr)* - $130.000 CLP
8️⃣ *Veleiro Akimbo 4p (1.5hr)* - $140.000 CLP
9️⃣ *Veleiro Akimbo 5p (1.5hr)* - $150.000 CLP
🔟 *Veleiro Akimbo 5p (1.5hr)* - $160.000 CLP

*Qual opção você prefere?*

Digite o número da sua escolha (1-10)

💡 *Lembre-se:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
    },
    
    # Ask for number of people
    "experience_ask_people": {
        "es": """👥 *¿Cuántas personas participarán?*

Por favor escribe el número de personas

(El precio se calculará automáticamente)

💡 *Recuerda:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """👥 *How many people will participate?*

Please type the number of people

(The price will be calculated automatically)

💡 *Remember:* Type *"Menu"* to return to *HotBoat Menu* 🚤""",
        
        "pt": """👥 *Quantas pessoas participarão?*

Por favor digite o número de pessoas

(O preço será calculado automaticamente)

💡 *Lembre-se:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
    },
    
    # Experience confirmation
    "experience_added_to_cart": {
        "es": """✅ *Experiencia Agregada al Carrito*

🎯 *{name}*
👥 {quantity}
💰 ${total:,} CLP

{cart}

━━━━━━━━━━━━━━━━

💡 *Opciones:*

• Escribe *"Menu"* para agregar más experiencias o actividades
• Escribe *"Carrito"* para ver tu carrito
• Escribe *"Confirmar"* o *"Proceder con pago"* cuando estés listo

🚤 ¡Seguimos construyendo tu aventura perfecta!""",
        
        "en": """✅ *Experience Added to Cart*

🎯 *{name}*
👥 {quantity}
💰 ${total:,} CLP

{cart}

━━━━━━━━━━━━━━━━

💡 *Options:*

• Type *"Menu"* to add more experiences or activities
• Type *"Cart"* to view your cart
• Type *"Confirm"* or *"Proceed to payment"* when ready

🚤 Let's keep building your perfect adventure!""",
        
        "pt": """✅ *Experiência Adicionada ao Carrinho*

🎯 *{name}*
👥 {quantity}
💰 ${total:,} CLP

{cart}

━━━━━━━━━━━━━━━━

💡 *Opções:*

• Digite *"Menu"* para adicionar mais experiências ou atividades
• Digite *"Carrinho"* para ver seu carrinho
• Digite *"Confirmar"* ou *"Proceder ao pagamento"* quando estiver pronto

🚤 Vamos continuar construindo sua aventura perfeita!"""
    },
    
    "experience_confirmation": {
        "es": """✅ *Solicitud de Experiencia Recibida*

{summary}

*El Capitán Tomás revisará tu solicitud y te contactará pronto para confirmar disponibilidad y coordinar detalles.* 👨‍✈️⚓

🙏 ¡Gracias por elegir HotBoat Chile!

💡 *Recuerda:* Escribe *"Menu"* para volver al *Menú HotBoat* 🚤""",
        
        "en": """✅ *Experience Request Received*

{summary}

*Captain Tomás will review your request and contact you soon to confirm availability and coordinate details.* 👨‍✈️⚓

🙏 Thank you for choosing HotBoat Chile!

💡 *Remember:* Type *"Menu"* to return to *HotBoat Menu* 🚤""",
        
        "pt": """✅ *Pedido de Experiência Recebido*

{summary}

*O Capitão Tomás revisará seu pedido e te contatar\u00e1 em breve para confirmar disponibilidade e coordenar detalhes.* 👨‍✈️⚓

🙏 Obrigado por escolher HotBoat Chile!

💡 *Lembre-se:* Digite *"Menu"* para voltar ao *Menu HotBoat* 🚤"""
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


LANGUAGE_KEYWORD_MAP = {
    "es": ["español", "espanol", "spanish"],
    "en": ["inglés", "ingles", "english"],
    "pt": ["portugués", "portugues", "português", "portuguese"],
    "fr": ["francés", "frances", "français", "francais", "french"],
    "de": ["alemán", "aleman", "german", "deutsch"],
    "it": ["italiano", "italian", "italien"]
}

LANGUAGE_FLAG_EMOJIS = ["🇨🇱", "🇪🇸", "🇺🇸", "🇧🇷", "🇫🇷", "🇩🇪", "🇮🇹"]


def _normalize_language_phrase(message: str) -> str:
    normalized = message.lower().strip()
    for flag in LANGUAGE_FLAG_EMOJIS:
        normalized = normalized.replace(flag, "")
    # Remove extra spaces introduced by emojis
    return " ".join(normalized.split())


def get_language_code_from_text(message: str) -> Optional[str]:
    """
    Detect if the message explicitly references a language and return its code.
    Supports Spanish, English, Portuguese, French, German and Italian keywords.
    """
    if not message:
        return None
    normalized_message = _normalize_language_phrase(message)
    for code, keywords in LANGUAGE_KEYWORD_MAP.items():
        if normalized_message in keywords:
            return code
    return None


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
        "español", "spanish",
        "english", "inglés", "ingles",
        "português", "portugues", "portuguese",
        "francés", "frances", "français", "francais", "french",
        "alemán", "aleman", "german", "deutsch",
        "italiano", "italian", "italien",
        "🌍"
    ]
    
    return any(keyword in message_lower for keyword in language_keywords)

