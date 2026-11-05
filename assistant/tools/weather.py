"""ventana_tratamiento: si se puede tratar los próximos días (umbrales de weather/treatment_rules.py)."""
from datetime import date

from django.conf import settings

from assistant.tools.base import ToolError, arg_int, arg_list, fmt_date, fmt_num, make_table, register, result
from assistant.tools.resolve import resolve_fields
from farm.models import Field

LEVELS = {'ok': 'Sí', 'warn': 'Dudoso', 'bad': 'No'}


@register(
    'ventana_tratamiento',
    'Previsión AEMET por municipio de las parcelas para los próximos días: si se puede pulverizar '
    '(Sí / Dudoso / No), probabilidad de lluvia y viento.',
    {
        'parcelas': {'type': 'array', 'items': {'type': 'string'}},
        'cultivo': {'type': 'array', 'items': {'type': 'string'}},
        'dias': {'type': 'integer', 'description': 'De 1 a 7. Por defecto, 3.'},
    },
    flag='WEATHER',
)
def ventana_tratamiento(ctx, args):
    from weather import services

    if not getattr(settings, 'AEMET_API_KEY', ''):
        raise ToolError('La previsión del tiempo no está configurada.')
    # AEMET puede tardar hasta SUMMARY_BUDGET s; si no queda margen, mejor no empezar
    if ctx.remaining() < services.SUMMARY_BUDGET + 5:
        raise ToolError('No da tiempo a consultar AEMET en esta pregunta: que la haga sola.')
    days = arg_int(args, 'dias', 3, 1, 7)
    names, crops = arg_list(args, 'parcelas'), arg_list(args, 'cultivo')
    fields = resolve_fields(ctx.organization, names, crops) if (names or crops) else \
        list(Field.objects.filter(organization=ctx.organization))
    with_geo = [f for f in fields if f.geometry]
    if not with_geo:
        raise ToolError('Ninguna de esas parcelas tiene el contorno dibujado, y sin él no hay previsión.')
    summary = services.get_weather_summary(with_geo)

    rows = []
    for muni in summary['municipalities']:
        label = f'{muni["name"]} ({", ".join(f["name"] for f in muni["fields"])})'
        for day in muni['daily']:
            when = date.fromisoformat(day['date'][:10])
            if when < ctx.today or (when - ctx.today).days >= days:
                continue
            rows.append([label, fmt_date(when), LEVELS.get(day['level'], day['level']),
                         f'{day["max_precipitation_probability"]} %', f'{fmt_num(day["max_wind_speed"], 0)} km/h'])
    notes = [f'Sin previsión para {", ".join(e["fields"])}: {e["reason"]}' for e in summary['errors']]
    notes.append('Sí = lluvia < 20 % y viento ≤ 20 km/h; No = lluvia ≥ 50 % o viento > 25 km/h.')
    table = make_table('¿Se puede tratar?', ['Municipio', 'Día', 'Tratar', 'Lluvia', 'Viento'], rows, notes,
                       numeric=(3, 4))
    return result(table, [', '.join(f.name for f in with_geo), f'Próximos {days} días'])
