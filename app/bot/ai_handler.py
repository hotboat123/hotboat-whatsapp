"""
AI Handler using OpenAI SDK with Groq backend (OpenAI-compatible API)
Supports MCP (Model Context Protocol) servers
"""
import logging
import json
from typing import List, Dict, Optional, Any
from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

try:
    from app.bot.mcp_handler import MCPHandler
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("MCP handler not available - running without MCP support")

settings = get_settings()

DEFAULT_MODEL = "llama-3.3-70b-versatile"  # Groq model name (updated from deprecated llama-3.1-70b-versatile)


def _default_editable_prompt() -> str:
    """The character/tone/business-info portion of the system prompt — the
    part an operator can override per A/B variant (bot_ab_variants.
    system_prompt). Kept separate from SAFETY_FOOTER below so a custom
    prompt can never accidentally drop the anti-hallucination rules."""
    return f"""Eres un asistente virtual de {settings.business_name}, una empresa de tours en bote en Villarrica, Chile.

INFORMACIÓN DEL NEGOCIO:
- Nombre: {settings.business_name}
- Teléfono: {settings.business_phone}
- Email: {settings.business_email}
- Sitio web: {settings.business_website}

PERSONAJE:
Soy Popeye el Marino, cabo segundo del HotBoat Chile 🚤
Mantengo el barco a flote y ayudo a los pasajeros que llegan buscando una experiencia única entre burbujas calientes 🌊🔥
Si no logro resolver tu duda, el Capitán Tomás tomará el timón 👨‍✈️

SERVICIOS:
- HotBoat Trip: Paseos en tina caliente flotante con motor eléctrico por la Laguna Rivera, rodeada de naturaleza 🌿
- Capacidades disponibles: 2, 3, 4, 5, 6 o 7 personas
- Experiencia única de relajación y vistas increíbles, como en aguas termales 💦

PRECIOS POR PERSONA (según número de personas):
- 2 personas: $76,990 por persona (Total: $153,980)
- 3 personas: $59,990 por persona (Total: $179,970)
- 4 personas: $48,990 por persona (Total: $195,960)
- 5 personas: $42,990 por persona (Total: $214,950)
- 6 personas: $36,990 por persona (Total: $221,940)
- 7 personas: $33,990 por persona (Total: $237,930)
Niños de 0 a 12 años: $10.000 de descuento por cada niño sobre el total (los niños SÍ cuentan en el número de personas para elegir la tarifa)

PERSONALIDAD:
- Marinero rudo pero simpático ⚓
- Habla con expresiones marineras (“Ahoy”, “Aye aye, capitán”, “Por todos los mares”)
- Cercano, con humor y siempre dispuesto a ayudar
- Respuestas cortas y claras (máximo 2-3 párrafos)
- Usa emojis náuticos y divertidos ocasionalmente ⛵🥬💪

FUNCIONES:
1. Responder preguntas sobre los servicios del HotBoat
2. Ayudar a consultar disponibilidad
3. Guiar el proceso de reserva
4. Dar información sobre precios
5. Responder dudas generales y mantener buen humor de marinero

IMPORTANTE:
- Si preguntan por disponibilidad específica, di que vas a consultar y responde con la información real.
- Si preguntan por precios y mencionan el número de personas, usa la tabla de PRECIOS POR PERSONA arriba para dar el precio EXACTO.
- Si preguntan por precios sin especificar número de personas, menciona que los precios van desde $33,990 a $76,990 por persona según el grupo.
- Siempre mantén un tono cortés, profesional y divertido.
- Si no sabes algo, admítelo y ofrece contactar con el Capitán Tomás.
- Mantén el estilo marinero, pero sin exagerar: que el cliente sienta que habla con un ayudante real del barco."""


# Anti-hallucination / anti-overpromise rules — ALWAYS appended after the
# editable prompt above, whether it's the default or a per-variant custom
# one (bot_ab_variants.system_prompt). Never exposed to the admin UI as
# editable: dropping these by accident (e.g. a shorter custom prompt that
# forgot to restate them) would let the AI promise things the business
# can't actually do — claim a fake email confirmation, or claim it added a
# reservation to the cart when only the deterministic bot code can.
SAFETY_FOOTER = """PROCESO DE RESERVA (MUY IMPORTANTE):
- NUNCA digas que una reserva está "confirmada" automáticamente.
- NUNCA menciones "correo de confirmación", "mail de confirmación" o "email de confirmación".
- NO existe un sistema automático de confirmación por correo.
- Cuando un cliente agrega algo al carrito, di que el Capitán Tomás se comunicará con ellos para finalizar.
- El Capitán Tomás gestiona TODAS las confirmaciones manualmente por WhatsApp o teléfono.
- Si preguntan por confirmación, di: "El Capitán Tomás se comunicará contigo pronto para confirmar todos los detalles 👨‍✈️"

LIMITACIONES TÉCNICAS (CRÍTICO):
- TÚ NO PUEDES agregar reservas al carrito. Solo el sistema automático puede hacerlo.
- NUNCA digas "he agregado al carrito" o "agregué tu reserva" porque NO es verdad.
- Si un cliente pide reservar pero no especifica fecha/hora/personas claramente, NO inventes que agregaste algo.
- En su lugar, pídeles que escriban la fecha, hora y número de personas en un mensaje.
- Ejemplo: "Para reservar, dime la fecha, hora y número de personas. Por ejemplo: 'martes para 3 personas a las 18'"

Responde en español chileno de manera natural y amigable."""


def build_system_prompt(custom_prompt: Optional[str] = None) -> str:
    """The editable part (default, or a variant's override) plus the fixed
    safety footer — see SAFETY_FOOTER's docstring for why it's never
    skippable."""
    body = (custom_prompt or "").strip() or _default_editable_prompt()
    return f"{body}\n\n{SAFETY_FOOTER}"


class AIHandler:
    """Handle AI responses using OpenAI SDK with Groq backend and MCP support"""

    def __init__(self, model: Optional[str] = None, custom_prompt: Optional[str] = None):
        # Use OpenAI SDK but point to Groq's OpenAI-compatible API
        self.client = OpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1"  # Groq's OpenAI-compatible endpoint
        )
        self.model = model or DEFAULT_MODEL

        if MCP_AVAILABLE:
            self.mcp_handler = MCPHandler()
            self._initialize_mcp_servers()
        else:
            self.mcp_handler = None

        # System prompt for the bot — custom_prompt lets an A/B variant
        # override the editable part (see build_system_prompt()); the
        # safety-critical footer is always appended regardless.
        self.system_prompt = build_system_prompt(custom_prompt)
    
    def _initialize_mcp_servers(self):
        """
        Initialize MCP servers from configuration
        Can be extended to load from environment variables or config file
        """
        # Example: Add MCP servers here
        # self.mcp_handler.add_mcp_server("example", {
        #     "url": "https://mcp-server.example.com",
        #     "api_key": None,
        #     "tools": [
        #         {
        #             "name": "get_weather",
        #             "description": "Get current weather",
        #             "parameters": {
        #                 "type": "object",
        #                 "properties": {
        #                     "location": {"type": "string", "description": "City name"}
        #                 }
        #             }
        #         }
        #     ]
        # })
        pass
    
    async def generate_response(
        self,
        message_text: str,
        conversation_history: List[Dict],
        contact_name: str
    ) -> str:
        """
        Generate AI response using Groq via OpenAI SDK
        
        Args:
            message_text: Current message
            conversation_history: Previous messages
            contact_name: User's name
        
        Returns:
            AI-generated response
        """
        try:
            # Build messages for AI (last 10 messages for context)
            messages = []
            recent_history = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history
            
            for msg in recent_history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Get available tools from MCP servers if enabled
            tools = None
            if self.mcp_handler and self.mcp_handler.enabled:
                available_tools = self.mcp_handler.get_available_tools()
                if available_tools:
                    tools = available_tools
                    logger.info(f"Using {len(tools)} MCP tools for this request")
            
            # Call Groq API (supports OpenAI-compatible function calling)
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    *messages
                ],
                "max_tokens": 500,
                "temperature": 0.7
            }
            
            # Add tools if MCP is enabled and tools are available
            if tools:
                api_params["tools"] = tools
                api_params["tool_choice"] = "auto"  # Let model decide when to use tools
            
            response = self.client.chat.completions.create(**api_params)
            
            # Extract response text
            message = response.choices[0].message
            
            # Check if model wants to call a tool (MCP function calling)
            if message.tool_calls:
                logger.info(f"Model requested {len(message.tool_calls)} tool calls")
                
                # Process tool calls
                tool_responses = []
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    # Safely parse tool arguments (JSON)
                    try:
                        tool_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in tool arguments: {tool_call.function.arguments}")
                        tool_args = {}
                    
                    # Call MCP tool
                    tool_result = await self.mcp_handler.call_mcp_tool(tool_name, tool_args)
                    
                    tool_responses.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_name,
                        "content": str(tool_result) if tool_result else "Tool execution failed"
                    })
                
                # Make second API call with tool results
                messages_with_tools = [
                    {"role": "system", "content": self.system_prompt},
                    *messages,
                    {"role": "assistant", "content": message.content, "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in message.tool_calls
                    ]},
                    *tool_responses
                ]
                
                # Get final response with tool results
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages_with_tools,
                    max_tokens=500,
                    temperature=0.7
                )
                
                response_text = final_response.choices[0].message.content
            else:
                # Normal response without tool calls
                response_text = message.content
            
            logger.info(f"AI response generated: {response_text[:100]}...")
            
            return response_text
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback response (estilo Popeye)
            return f"""🥬 ¡Ahoy, grumete! ⚓  



Soy *Popeye el Marino*, cabo segundo del *HotBoat Chile* 🚤  

Estoy al mando para ayudarte con todas tus consultas sobre nuestras experiencias flotantes 🌊  

Puedes preguntarme por:  

1️⃣ *Disponibilidad y horarios*  

2️⃣ *Precios por persona*  

3️⃣ *Características del HotBoat*  

4️⃣ *Extras y promociones*  

5️⃣ *Ubicación y reseñas*  

Si prefieres hablar con el *Capitán Tomás*, escribe *Llamar a Tomás*, *Ayuda*, o simplemente *6️⃣* 👨‍✈️🌿  

¿Listo para zarpar o qué número eliges, grumete?"""








