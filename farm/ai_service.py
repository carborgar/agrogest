"""
Servicio de integración con Google Gemini AI para el asistente de AgroGest.

Modelo recomendado: gemini-2.0-flash-lite
  - Tier gratuito: 30 RPM, 1.500 req/día, 1 M tokens/minuto
  - Mejor ratio límite-calidad del mercado a fecha 2025-2026

Configura en .env:
  GEMINI_API_KEY=tu_clave_aqui
  GEMINI_MODEL=gemini-2.0-flash-lite   (opcional, este es el default)

Obtén tu clave GRATIS en: https://aistudio.google.com/apikey
"""

import json
import logging
import re
from datetime import date

from google import genai
from google.genai import types
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_TREATMENTS_CONTEXT = 200

# Regex para detectar secuencias \uXXXX literales que algunos modelos emiten como texto plano
_UNICODE_ESCAPE_RE = re.compile(r'\\u([0-9a-fA-F]{4})')


def normalize_ai_response(text: str) -> str:
    """
    Algunos modelos devuelven secuencias \\uXXXX literales (ej. \\u000A en vez de \\n).
    Las convertimos a sus caracteres reales para que Markdown se renderice bien.
    """
    return _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def get_org_context(organization) -> dict:
    """
    Construye un diccionario con todos los datos relevantes de la organización
    para inyectar en el prompt del asistente.
    """
    from farm.models import Field, Product, Treatment, Machine

    # ── Productos ──────────────────────────────────────────────────────────
    products = (
        Product.objects
        .filter(organization=organization)
        .select_related('product_type')
        .order_by('name')
    )
    products_list = []
    for p in products:
        pd: dict = {
            'id': p.pk,
            'url': f'/productos/{p.pk}/editar/',
            'nombre': p.name,
            'tipo': p.product_type.name,
        }
        if p.supports_spraying:
            pd['dosis_pulverización'] = f"{p.spraying_dose} {p.get_dose_type_name('spraying')}"
            pd['dose_type_pulv'] = p.spraying_dose_type
            pd['dose_value_pulv'] = float(p.spraying_dose)
        if p.supports_fertigation:
            pd['dosis_fertirrigación'] = f"{p.fertigation_dose} {p.get_dose_type_name('fertigation')}"
        if p.price:
            pd['precio_por_unidad'] = float(p.price)
        if p.comments:
            pd['comentarios'] = p.comments
        products_list.append(pd)

    # ── Parcelas ───────────────────────────────────────────────────────────
    fields = Field.objects.filter(organization=organization).order_by('name')
    fields_list = [
        {
            'id': f.pk,
            'url': f'/parcelas/{f.pk}/',
            'nombre': f.name,
            'hectáreas': float(f.area),
            'cultivo': f.crop,
            'año_plantación': f.planting_year,
        }
        for f in fields
    ]

    # ── Máquinas ───────────────────────────────────────────────────────────
    machines = Machine.objects.filter(organization=organization).order_by('name')
    machines_list = [
        {'nombre': m.name, 'tipo': m.type, 'capacidad_litros': m.capacity}
        for m in machines
    ]

    # ── Tratamientos (historial completo, máx. MAX_TREATMENTS_CONTEXT) ────────
    treatments = (
        Treatment.objects
        .filter(organization=organization)
        .select_related('field', 'machine')
        .prefetch_related('treatmentproduct_set__product__product_type')
        .order_by('-date')[:MAX_TREATMENTS_CONTEXT]
    )
    treatments_list = []
    for t in treatments:
        tc: dict = {
            'id': t.pk,
            'url': f'/tratamientos/{t.pk}',
            'nombre': t.name,
            'parcela': t.field.name,
            'tipo': t.get_type_display(),
            'fecha': t.date.strftime('%d/%m/%Y'),
            'estado': t.get_status_display(),
        }
        if t.machine:
            tc['máquina'] = f"{t.machine.name} ({t.machine.capacity}L)"
        if t.actual_water_per_ha():
            tc['mojado_L_ha'] = t.actual_water_per_ha()
        productos_en_trat = [
            f"{tp.product.name} [tipo: {tp.product.product_type.name}]: "
            f"{tp.dose} {tp.dose_type} (total {tp.total_dose} {tp.total_dose_unit})"
            for tp in t.treatmentproduct_set.all()
        ]
        if productos_en_trat:
            tc['productos'] = productos_en_trat
        treatments_list.append(tc)

    return {
        'productos': products_list,
        'parcelas': fields_list,
        'máquinas': machines_list,
        'tratamientos': treatments_list,  # historial completo (más reciente primero)
    }


def build_system_prompt(organization, context: dict) -> str:
    today = date.today().strftime('%d/%m/%Y')
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    return f"""Eres AgroGest Asistente, un asistente virtual de gestión agrícola integrado en la aplicación AgroGest.

Organización: {organization.name}
Fecha actual: {today}

## Capacidades
- Responder preguntas sobre los datos de la organización: productos, parcelas, máquinas y tratamientos.
- Realizar cálculos de dosis de productos.
- Consultar el historial de tratamientos.
- Dar recomendaciones agrícolas generales.

## Fórmulas de cálculo de dosis

**Dosis en L/1000L o kg/1000L (concentración en caldo):**
  cantidad_por_carga = dosis × capacidad_máquina / 1000

**Dosis en L/ha o kg/ha (por superficie):**
  total_parcela = dosis × hectáreas_parcela
  cantidad_por_carga = dosis × (capacidad_máquina / mojado_L_ha)

**Dosis en % (porcentaje de caldo):**
  cantidad_por_carga = (dosis / 100) × capacidad_máquina

**Para calcular compra necesaria:**
  litros_agua_total = hectáreas × mojado_L_ha
  cargas_necesarias = litros_agua_total / capacidad_máquina
  producto_necesario = dosis_por_carga × cargas_necesarias

## Datos actuales de la organización
```json
{context_json}
```

## Instrucciones de respuesta
- Responde siempre en español, de forma clara y concisa.
- En cálculos, muestra los pasos intermedios con los valores concretos.
- Si falta información necesaria para un cálculo (ej. mojado L/ha, capacidad de máquina o hectáreas), pídela amablemente.
- Si no tienes datos suficientes, dilo con claridad en vez de inventar.

### Presentación — cuida el formato, la app lo renderiza en Markdown

**Texto:**
- Usa **negrita** para nombres de parcelas, productos y tratamientos.
- Usa `código inline` para cifras con unidades: `500 L/ha`, `2.5 kg/ha`, `15/09/2025`.
- No uses bloques de código para texto normal, solo para secuencias de comandos o JSON.

**Listas:**
- Usa listas con viñetas (`-`) para enumerar elementos sin orden relevante.
- Usa listas numeradas para pasos de un cálculo o procedimiento.
- No abuses: si hay 2 elementos, escríbelos en línea separados por ` · `.

**Tablas:**
- Úsalas cuando compares varios elementos con los mismos atributos
  (ej. varios tratamientos, varios productos con sus dosis).
- Columnas recomendadas para tratamientos: Tratamiento | Fecha | Parcela | Productos.
- Columnas recomendadas para productos: Producto | Tipo | Dosis pulv. | Dosis fertig.
- Mantén las tablas compactas: no incluyas columnas vacías.

**Citas / fichas de entidad** (blockquote `>`):
- Úsalas para mostrar los detalles de UNA entidad concreta.
- Formato de tratamiento:
  > **[Nombre](/url)** · `fecha` · [Parcela](/url_parcela)
  > 🚜 Máquina: nombre (capacidadL) · 💧 Mojado: `X L/ha`
  > - [Producto A](/url) [Tipo] — `dosis`
  > - [Producto B](/url) [Tipo] — `dosis`
- Formato de parcela:
  > **[Nombre parcela](/url)** · `X ha` · Cultivo: nombre (`año`)
- Formato de producto:
  > **[Nombre producto](/url)** · Tipo: X · Pulv.: `X L/1000L` · Precio: `X €/ud`

**Separadores:**
- Usa `---` para separar bloques cuando la respuesta tenga varias secciones claramente distintas.

**Emojis (con moderación):**
- 🌿 parcelas / cultivo · 💧 agua / riego · 🧪 producto / tratamiento
- 📅 fechas · 🚜 maquinaria · 🛒 compras · ✅ completado · ⚠️ atrasado

### Cómo presentar entidades concretas

Combina **siempre** el enlace con los detalles más relevantes.
Adapta el nivel de detalle al contexto: si es un solo elemento, muestra todo;
si son varios en lista, muestra solo los campos clave para no sobrecargar.

## Cómo interpretar los datos para consultas

**Búsquedas por tipo de producto** (ej. "insecticida", "fungicida", "herbicida", "abono"...):
- La sección `productos` tiene el campo `tipo` de cada producto registrado.
- La sección `tratamientos` contiene el historial completo ordenado de más reciente a más antiguo.
  Cada producto dentro de un tratamiento aparece como:
  `NombreProducto [tipo: TipoProducto]: dosis ...`
- Para responder "¿cuándo fue la última vez que traté la parcela X con insecticida?":
  1. Filtra los tratamientos cuya clave `parcela` coincida con X (sin importar mayúsculas/tildes).
  2. En cada tratamiento, mira la lista `productos` y busca los que contengan `[tipo: Insecticida]`
     (coincidencia flexible, sin distinguir mayúsculas ni tildes).
  3. Como los tratamientos ya vienen ordenados del más reciente al más antiguo,
     el primero que cumpla la condición es la respuesta.
  4. Si no encuentras ninguno, indícalo claramente.
- Si el usuario no especifica parcela, busca en todas las parcelas.

**Búsquedas por nombre de producto** (ej. "Brotomax", "Confidor"...):
- Busca coincidencia parcial e insensible a mayúsculas en el nombre del producto
  dentro de los tratamientos Y en la sección `productos`.

**Preguntas de resumen o "¿qué productos he usado?":**
- Recorre todos los tratamientos y extrae los productos únicos mencionados.
- Agrupa por tipo si el usuario lo pide.
- Indica cuántas veces se ha usado cada producto si es relevante.
"""


def chat_with_ai(organization, user_message: str, history_messages) -> tuple:
    """
    Envía un mensaje a Gemini AI y devuelve la respuesta.

    Args:
        organization: instancia de Organization
        user_message: texto del mensaje del usuario
        history_messages: QuerySet/lista de ChatMessage anteriores

    Returns:
        (response_text, None) en éxito
        (None, error_message) en error
    """
    api_key = getattr(settings, 'GEMINI_API_KEY', None) or ''
    if not api_key:
        return None, (
            "⚙️ No hay clave de API configurada. "
            "El administrador debe añadir GEMINI_API_KEY en el fichero .env."
        )

    try:
        client = genai.Client(api_key=api_key)

        context = get_org_context(organization)
        system_prompt = build_system_prompt(organization, context)

        model_name = getattr(settings, 'GEMINI_MODEL', 'gemini-2.0-flash-lite')

        # Convertir historial al formato de la nueva SDK
        gemini_history = []
        for msg in history_messages:
            role = 'user' if msg.role == 'user' else 'model'
            gemini_history.append(
                types.Content(role=role, parts=[types.Part(text=msg.content)])
            )

        chat = client.chats.create(
            model=model_name,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
            history=gemini_history,
        )

        response = chat.send_message(user_message)
        return normalize_ai_response(response.text), None

    except Exception as exc:
        error_str = str(exc)
        logger.warning("Gemini API error [org=%s]: %s", organization.id, error_str)

        if any(k in error_str for k in ('429', 'RESOURCE_EXHAUSTED', 'quota', 'rate limit')):
            return None, (
                "⚠️ **Límite diario alcanzado.** Se han agotado las consultas gratuitas del día "
                "para el modelo Gemini. Los límites se reinician cada día a las 00:00 UTC "
                "(02:00h en verano / 01:00h en invierno en España). ¡Hasta mañana! 🌙"
            )
        if any(k in error_str for k in ('403', 'API_KEY_INVALID', 'invalid api key')):
            return None, "❌ Clave de API no válida. Revisa la configuración en .env (GEMINI_API_KEY)."

        return None, f"❌ Error inesperado al conectar con el asistente. Detalles: {error_str}"
