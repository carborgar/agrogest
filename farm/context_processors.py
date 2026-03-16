def sidebar_state(request):
    return {
        'sidebar_collapsed': request.COOKIES.get('sidebar_collapsed', 'false') == 'true'
    }


# Mapeo: clave de contexto → lista de url_names que activan ese ítem
_NAV_GROUPS = {
    'nav_home':         {'field_list'},
    'nav_fields':       {'field-list', 'field-create', 'field-detail', 'field-edit'},
    'nav_treatments':   {'treatment-list', 'treatment-create', 'treatment-detail'},
    'nav_calendar':     {'treatment-calendar'},
    'nav_costs':        {'field-costs'},
    'nav_expenses':     {'expense-list', 'expense-create', 'expense-edit'},
    'nav_shopping':     {'treatment-shopping-list'},
    'nav_harvests':     {'harvest-summary', 'harvest-create', 'harvest-edit'},
    'nav_expense_types':{'expense-type-list', 'expense-type-create', 'expense-type-edit'},
    'nav_products':     {'product-list', 'product-create', 'product-edit'},
    'nav_product_types':{'product-type-list', 'product-type-create', 'product-type-edit'},
}


def active_nav(request):
    """
    Inyecta en el contexto un booleano por cada grupo de navegación,
    más dos helpers para los grupos colapsables:
      nav_gastos_open   → True si hay que mostrar el submenu de Gastos abierto
      nav_products_open → True si hay que mostrar el submenu de Productos abierto
    """
    url_name = getattr(request.resolver_match, 'url_name', '') or ''
    ctx = {key: url_name in names for key, names in _NAV_GROUPS.items()}
    ctx['nav_gastos_open']   = ctx['nav_costs'] or ctx['nav_expenses']
    ctx['nav_products_open'] = ctx['nav_products'] or ctx['nav_product_types']
    return ctx
