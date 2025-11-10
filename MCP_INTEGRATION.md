# 🔌 Integración MCP (Model Context Protocol)

## ✅ Estado Actual

El bot ahora tiene **compatibilidad completa con MCP servers** gracias a Groq, que soporta el protocolo compatible con OpenAI function calling.

## 🎯 ¿Qué es MCP?

**Model Context Protocol (MCP)** es un protocolo desarrollado por Anthropic que permite que los modelos de IA se conecten con servicios externos y herramientas en tiempo real. Esto permite:

- Conectarse a bases de datos
- Interactuar con APIs externas
- Usar herramientas de navegación web
- Integrar con servicios como GitHub, Stripe, etc.

## 🚀 Cómo Funciona con Groq

Groq tiene soporte nativo para **function calling** compatible con OpenAI, lo que significa que:

1. ✅ El modelo puede decidir cuándo usar herramientas
2. ✅ Las herramientas se llaman automáticamente cuando el modelo las necesita
3. ✅ El resultado de la herramienta se incluye en la respuesta final

## 📁 Archivos Creados

### `app/bot/mcp_handler.py`
Maneja las conexiones a servidores MCP y la ejecución de herramientas.

**Características:**
- Gestión de múltiples servidores MCP
- Registro de herramientas disponibles
- Ejecución de llamadas a herramientas
- Formato compatible con OpenAI function calling

### `app/bot/ai_handler.py` (actualizado)
Ahora incluye:
- Soporte para MCP handlers
- Detección automática de herramientas disponibles
- Manejo de tool calling del modelo
- Respuestas con contexto de herramientas

## 🔧 Cómo Agregar Servidores MCP

### Paso 1: Configurar un Servidor MCP

Edita `app/bot/ai_handler.py` y agrega tu servidor en el método `_initialize_mcp_servers()`:

```python
def _initialize_mcp_servers(self):
    """Initialize MCP servers from configuration"""
    
    # Ejemplo: Servidor MCP para base de datos
    self.mcp_handler.add_mcp_server("database", {
        "url": "https://mcp-server.example.com",
        "api_key": None,
        "tools": [
            {
                "name": "query_database",
                "description": "Query the database for customer information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "SQL query to execute"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
    })
    
    # Ejemplo: Servidor MCP para clima
    self.mcp_handler.add_mcp_server("weather", {
        "url": "https://weather-mcp.example.com",
        "api_key": "your_api_key",
        "tools": [
            {
                "name": "get_weather",
                "description": "Get current weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name or coordinates"
                        }
                    },
                    "required": ["location"]
                }
            }
        ]
    })
```

### Paso 2: Implementar la Comunicación con el Servidor

El método `call_mcp_tool` en `mcp_handler.py` necesita implementar la comunicación real con el servidor MCP. Actualmente es un placeholder que debes completar según tu servidor MCP.

**Ejemplo de implementación:**

```python
async def call_mcp_tool(
    self, 
    tool_name: str, 
    arguments: Dict[str, Any]
) -> Optional[Any]:
    """Call a tool from an MCP server"""
    import httpx
    
    # Find which server has this tool
    for server_name, config in self.mcp_servers.items():
        server_tools = config.get("tools", [])
        for tool in server_tools:
            if tool.get("name") == tool_name:
                url = config.get("url")
                api_key = config.get("api_key")
                
                # Make HTTP request to MCP server
                async with httpx.AsyncClient() as client:
                    headers = {}
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
                    
                    response = await client.post(
                        f"{url}/tools/{tool_name}",
                        json={"arguments": arguments},
                        headers=headers
                    )
                    
                    return response.json()
    
    return None
```

## 📋 Servidores MCP Disponibles

Groq tiene integraciones oficiales con varios servidores MCP:

- **BrowserBase MCP** - Navegación web
- **BrowserUse MCP** - Automatización de navegador
- **Exa MCP** - Búsqueda semántica
- **Firecrawl MCP** - Web scraping
- **HuggingFace MCP** - Modelos de ML
- **Parallel MCP** - Procesamiento paralelo
- **Stripe MCP** - Pagos
- **Tavily MCP** - Búsqueda web

## 🎯 Ejemplo de Uso

Cuando el modelo detecta que necesita usar una herramienta:

1. **Usuario pregunta:** "¿Qué tiempo hace en Villarrica?"
2. **Modelo detecta:** Necesita usar `get_weather`
3. **Sistema llama:** La herramienta automáticamente
4. **Resultado se incluye:** En la respuesta final

Todo esto ocurre **automáticamente** - el modelo decide cuándo usar las herramientas.

## ⚙️ Configuración

Por defecto, MCP está **deshabilitado** hasta que agregues servidores. Una vez que agregues servidores en `_initialize_mcp_servers()`, MCP se habilitará automáticamente.

## 🔍 Debugging

Para ver si MCP está funcionando, revisa los logs:

```
INFO: Using 2 MCP tools for this request
INFO: Model requested 1 tool calls
INFO: Calling MCP tool 'get_weather' from server 'weather'
```

## 📚 Recursos

- [Groq MCP Blog Post](https://groq.com/blog/introducing-remote-mcp-support-in-beta-on-groqcloud)
- [Groq MCP Server GitHub](https://github.com/groq/groq-mcp-server)
- [MCP Specification](https://modelcontextprotocol.io)

## ✅ Estado de Implementación

- ✅ Estructura base de MCP handler
- ✅ Integración con Groq function calling
- ✅ Soporte para múltiples servidores MCP
- ✅ Manejo automático de tool calling
- ⚠️ Implementación de comunicación HTTP con servidores MCP (pendiente - necesitas completar según tus servidores)

---

**Nota:** La estructura está lista. Solo necesitas implementar la comunicación real con tus servidores MCP específicos en el método `call_mcp_tool`.



