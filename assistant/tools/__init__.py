# Importar los módulos registra sus herramientas en base.REGISTRY.
from assistant.tools import calc, costs, pending, products, treatments, weather  # noqa: F401
from assistant.tools.base import ToolContext, ToolResult, available_tools, run_tool  # noqa: F401
