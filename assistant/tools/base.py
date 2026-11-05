"""
Infraestructura de las herramientas: registro, validación de argumentos y formato.

Cada herramienta recibe un `ToolContext` (usuario y organización, que pone la vista: nunca el modelo)
y los argumentos del modelo ya parseados. Devuelve un `ToolResult`:
  - text: lo que lee el modelo (compacto, tabular);
  - understood / table / candidates: lo que pinta la interfaz directamente, sin pasar por el modelo,
    para que las cifras que ve el usuario salgan del código y no de la redacción del modelo.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from typing import Callable

logger = logging.getLogger(__name__)

MAX_ROWS = 20


@dataclass
class ToolContext:
    user: object
    organization: object
    today: date
    remaining: Callable = lambda: 60.0  # segundos que quedan del plazo de la pregunta


@dataclass
class ToolResult:
    text: str
    understood: list = field(default_factory=list)
    table: dict | None = None
    candidates: list = field(default_factory=list)


class ToolError(Exception):
    """Error que se le explica al modelo (y, si hay candidatos, al usuario como botones)."""

    def __init__(self, message, candidates=()):
        super().__init__(message)
        self.candidates = list(candidates)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable
    flag: str = ''

    def schema(self):
        return {'type': 'function',
                'function': {'name': self.name, 'description': self.description, 'parameters': self.parameters}}


REGISTRY: list = []


def register(name, description, properties, required=(), flag=''):
    def decorator(func):
        REGISTRY.append(Tool(name, description,
                             {'type': 'object', 'properties': properties, 'required': list(required)},
                             func, flag))
        return func
    return decorator


def available_tools():
    """Se construye en cada petición para respetar los flags sin reiniciar."""
    from core.models import is_enabled
    return [t for t in REGISTRY if not t.flag or is_enabled(t.flag, default=False)]


def run_tool(tools_by_name, name, arguments, ctx):
    tool = tools_by_name.get(name)
    if tool is None:
        return ToolResult(text=f'ERROR: no existe la herramienta «{name}».')
    try:
        args = json.loads(arguments or '{}')
    except ValueError:
        return ToolResult(text='ERROR: argumentos JSON no válidos.')
    if not isinstance(args, dict):
        return ToolResult(text='ERROR: los argumentos deben ser un objeto JSON.')
    try:
        return tool.func(ctx, args)
    except ToolError as exc:
        text = f'ERROR: {exc}'
        if exc.candidates:
            text += ' Candidatos: ' + ', '.join(exc.candidates) + '.'
        return ToolResult(text=text, candidates=exc.candidates)
    except Exception:  # noqa: BLE001 — un fallo nuestro no debe tumbar la conversación
        logger.exception('Asistente: fallo en la herramienta %s', name)
        return ToolResult(text='ERROR: fallo interno al consultar los datos. Díselo al usuario.')


# ── Lectura de argumentos ────────────────────────────────────────────────────

def arg_list(args, key):
    value = args.get(key)
    if value in (None, ''):
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ToolError(f'«{key}» debe ser una lista.')
    return [str(v).strip() for v in value if str(v).strip()]


def arg_date(args, key, default=None):
    value = args.get(key)
    if not value:
        return default
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ToolError(f'«{key}» debe ser una fecha AAAA-MM-DD.') from None


def arg_decimal(value, key):
    if value in (None, ''):
        return None
    try:
        number = Decimal(str(value).replace(',', '.'))
    except InvalidOperation:
        raise ToolError(f'«{key}» debe ser un número.') from None
    if not number.is_finite() or number <= 0:
        raise ToolError(f'«{key}» debe ser un número mayor que 0.')
    return number


def arg_int(args, key, default, low, high):
    try:
        value = int(args.get(key) or default)
    except (TypeError, ValueError):
        value = default
    return min(max(value, low), high)


def applied_in(since, until, prefix='treatment__'):
    """Tratamientos aplicados en el periodo: por fecha de fin o, si no la tienen, por la prevista (como la app)."""
    return Q(**{f'{prefix}status': 'completed'}) & (
        Q(**{f'{prefix}finish_date__range': (since, until)})
        | Q(**{f'{prefix}finish_date__isnull': True, f'{prefix}date__range': (since, until)}))


def arg_choice(args, key, choices, default):
    value = args.get(key) or default
    if value not in choices:
        raise ToolError(f'«{key}» debe ser uno de: {", ".join(choices)}.')
    return value


# ── Formato (es-ES) ──────────────────────────────────────────────────────────

def fmt_num(value, decimals=2, strip=True):
    """1234.5 → «1.234,5». `strip` quita ceros finales (cantidades); no para euros."""
    if value is None:
        return '—'
    text = f'{Decimal(str(value)):,.{decimals}f}'
    if strip and '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text.replace(',', '\x00').replace('.', ',').replace('\x00', '.')


def fmt_eur(value):
    return '—' if value is None else f'{fmt_num(value, 2, strip=False)} €'


MONTHS = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')


def fmt_date(value):
    return f'{value.day} {MONTHS[value.month - 1]} {value.year}' if value else '—'


def make_table(title, columns, rows, notes=(), numeric=()):
    """Tabla para la interfaz. `numeric`: índices de columnas alineadas a la derecha."""
    extra = len(rows) - MAX_ROWS
    rows = [[str(c) for c in row] for row in rows[:MAX_ROWS]]
    notes = list(notes)
    if extra > 0:
        notes.append(f'… y {extra} más.')
    return {'title': title, 'columns': list(columns), 'rows': rows, 'notes': notes,
            'numeric': list(numeric)}


def table_text(table):
    """Tabla → texto compacto para el modelo (más corto que JSON con claves repetidas)."""
    lines = [table['title'], ' | '.join(table['columns'])]
    lines += [' | '.join(row) for row in table['rows']]
    lines += table['notes']
    return '\n'.join(lines)


def result(table, understood=()):
    return ToolResult(text=table_text(table), understood=list(understood), table=table)
