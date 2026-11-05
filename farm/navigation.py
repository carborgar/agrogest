"""
Definición única del menú de la app.

La usan las tres piezas de navegación, para que no se desordenen entre sí:
  - el lateral de escritorio (``_nav_items.html``),
  - la barra inferior del móvil (``menu.html``),
  - la hoja «Más» del móvil (``menu.html``): lo que no cabe en la barra.

Los grupos van por tarea, no por tipo de pantalla. El orden de las pestañas
del móvil va aparte (``TABS``) porque responde a la frecuencia de uso en el
campo, no al grupo.
"""
from dataclasses import dataclass, field
from typing import Callable

from django.urls import reverse


def _always(request) -> bool:
    return True


def request_flags(request) -> dict:
    """Feature flags de la petición, leídos una sola vez (la caché va en BD: cada lectura es una consulta)."""
    if not hasattr(request, '_feature_flags'):
        from core.models import get_all_flags
        request._feature_flags = get_all_flags()
    return request._feature_flags


def _assistant(request) -> bool:
    """Asistente: flag ASSISTANT encendido y clave del proveedor configurada."""
    from django.conf import settings
    return bool(request_flags(request).get('ASSISTANT', False) and settings.ASSISTANT_API_KEY
                and getattr(request.user, 'organization', None))


def _feature(name: str) -> Callable:
    """Visible solo si el feature flag existe y está activo (igual que antes en la plantilla)."""
    def check(request) -> bool:
        return bool(request_flags(request).get(name, False))
    return check


@dataclass(frozen=True)
class NavItem:
    key: str            # nav_xxx: booleano en el contexto si la página es de este ítem
    label: str
    icon: str           # clases de Font Awesome
    url_name: str
    tab_label: str = '' # etiqueta corta si es pestaña de la barra inferior
    match: tuple = ()   # otras url_name que también marcan el ítem como activo
    visible: Callable = field(default=_always, compare=False)


@dataclass(frozen=True)
class NavGroup:
    title: str          # vacío = sin título (Inicio)
    items: tuple
    as_list: bool = False  # en la hoja «Más»: lista en vez de cuadrícula (configuración)


NAV = (
    NavGroup('', (
        NavItem('nav_home', 'Inicio', 'fas fa-house', 'field_list', tab_label='Inicio'),
    )),
    NavGroup('Tratamientos', (
        NavItem('nav_treatments', 'Tratamientos', 'fas fa-droplet', 'treatment-list', tab_label='Tratamientos',
                match=('treatment-create', 'treatment-detail', 'treatment-edit', 'treatment-clone',
                       'treatment-repeat', 'treatment-finish', 'treatment-instructions')),
        NavItem('nav_calendar', 'Calendario', 'fas fa-calendar-days', 'treatment-calendar', tab_label='Calendario'),
        NavItem('nav_shopping', 'Preparar productos', 'fa fa-boxes-packing', 'treatment-shopping-list', tab_label='Preparar'),
        NavItem('nav_weather', 'El Tiempo', 'fa fa-cloud-sun', 'weather-overview', visible=_feature('WEATHER')),
        NavItem('nav_assistant', 'Asistente IA', 'fa fa-comments', 'assistant', visible=_assistant),
    )),
    NavGroup('Explotación', (
        # Las casetillas se gestionan dentro de Parcelas
        NavItem('nav_fields', 'Parcelas', 'fas fa-map-location-dot', 'field-list',
                match=('field-create', 'field-detail', 'field-edit', 'storage-point-list',
                       'storage-point-create', 'storage-point-detail', 'storage-point-edit')),
        # Tipos de producto y comparativa se gestionan dentro de Productos
        NavItem('nav_products', 'Productos', 'fa fa-box', 'product-list',
                match=('product-create', 'product-edit', 'product-type-list', 'product-type-create',
                       'product-type-edit', 'product-comparison')),
        NavItem('nav_harvests', 'Cosechas', 'fa fa-apple-whole', 'harvest-summary', match=('harvest-create', 'harvest-edit')),
    )),
    NavGroup('Economía', (
        NavItem('nav_expenses', 'Gastos', 'fa fa-receipt', 'expense-list', match=('expense-create', 'expense-edit')),
        NavItem('nav_costs', 'Informe de gastos', 'fa fa-chart-bar', 'field-costs'),
        NavItem('nav_stats', 'Estadísticas', 'fa fa-chart-line', 'yearly-stats'),
    )),
    NavGroup('Configuración', (
        NavItem('nav_expense_types', 'Tipos de gasto', 'fa fa-tags', 'expense-type-list',
                match=('expense-type-create', 'expense-type-edit')),
        NavItem('nav_treatment_cost_admin', 'Recálculo de costes', 'fa fa-calculator', 'treatment-cost-admin'),
    ), as_list=True),
)

# Pestañas de la barra inferior (móvil), en orden. Lo que más se usa en el campo.
TABS = ('nav_home', 'nav_treatments', 'nav_shopping', 'nav_calendar')

# Clave → url_name que la activan. Sale de NAV para no mantener dos listas.
NAV_MATCH = {
    item.key: frozenset((item.url_name, *item.match))
    for group in NAV for item in group.items
}

# Páginas de la sección «Cuenta» de la hoja «Más»: marcan la pestaña «Más».
ACCOUNT_URL_NAMES = frozenset({'notification-inbox', 'notification-preferences'})


def _url_name(request) -> str:
    return getattr(request.resolver_match, 'url_name', '') or ''


def active_flags(request) -> dict:
    """{nav_xxx: bool} según la url_name de la página actual."""
    url_name = _url_name(request)
    return {key: url_name in names for key, names in NAV_MATCH.items()}


def build_navigation(request, active: dict) -> dict:
    """
    Devuelve el menú listo para pintar.

    ``active`` es el dict {clave: bool} de ``active_nav``.
      nav_groups → grupos con sus ítems visibles (para el lateral)
      nav_tabs   → pestañas de la barra inferior, en orden
      nav_more   → grupos sin las pestañas (para la hoja «Más»); los vacíos no salen
      nav_more_active → True si la página actual está dentro de «Más»
    """
    groups, by_key = [], {}
    for group in NAV:
        items = []
        for item in group.items:
            if not item.visible(request):
                continue
            entry = {
                'key': item.key,
                'label': item.label,
                'icon': item.icon,
                'url': reverse(item.url_name),
                'tab_label': item.tab_label,
                'active': bool(active.get(item.key)),
            }
            items.append(entry)
            by_key[item.key] = entry
        if items:
            groups.append({'title': group.title, 'items': items, 'as_list': group.as_list})

    tabs = [by_key[k] for k in TABS if k in by_key]
    more = []
    for group in groups:
        rest = [i for i in group['items'] if i['key'] not in TABS]
        if rest:
            more.append({**group, 'items': rest})

    return {
        'nav_groups': groups,
        'nav_tabs': tabs,
        'nav_more': more,
        'nav_more_active': (any(i['active'] for g in more for i in g['items'])
                            or _url_name(request) in ACCOUNT_URL_NAMES),
    }
