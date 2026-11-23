"""
Últimos tratamientos hechos de cada parcela, con los parecidos marcados del mismo color.

Lo usan la vista «Por parcela» de Tratamientos y la tarjeta «Cómo van las parcelas» de Inicio.
No clasifica tandas: los parecidos (productos y nombre) salen de `farm.treatment_similarity`.
Solo cuentan los hechos (con fecha de finalización, no por `status`, que puede estar desfasado).
"""
from django.db.models import F, Window
from django.db.models.functions import RowNumber

from farm.models import Treatment, TreatmentProduct
from farm.treatment_similarity import group_similar, label_groups

COLORS = 12      # tonos .bf-c0…11 en treatment-styles.css; desde el 13.º grupo se repiten con borde discontinuo
COLOR_BASE = 10  # últimos hechos por parcela sobre los que se fijan los colores (el N más alto)


def last_per_field(queryset, limit):
    """Los `limit` hechos más recientes de cada parcela, en una sola consulta: numera los de cada
    parcela con Window y filtra sobre esa numeración (necesita Django ≥ 4.2)."""
    return (
        queryset
        .annotate(rank=Window(
            RowNumber(), partition_by=F('field_id'),
            order_by=[F('finish_date').desc(), F('date').desc(), F('id').desc()],
        ))
        .filter(rank__lte=limit)
        .order_by('field_id', 'rank')
        .prefetch_related('treatmentproduct_set__product')
    )


def field_history(user, all_fields, limit, filters=None, date_from=None, date_to=None):
    """
    Devuelve {'rows', 'groups', 'has_treatments', 'limit', 'columns'} (lo que pinta
    `farm/treatments/_by_field_table.html`).

    `all_fields`: parcelas de la organización (lista). `filters`: ids ya validados por nombre de
    parámetro ('field', 'type', 'product_types', 'products'). El periodo va sobre la fecha de
    finalización y los últimos `limit` se cuentan dentro de él. Las parcelas sin coincidencias
    siguen saliendo: que a una parcela le falte la pasada también es información.
    """
    f = {'field': [], 'type': [], 'product_types': [], 'products': [], **(filters or {})}

    # Base para los colores: los últimos 10 de cada parcela dentro del periodo, sin el resto de
    # filtros. Agrupando siempre sobre ella (más lo que se vea) un tratamiento no cambia de color
    # al cambiar N, la parcela, el tipo o el producto.
    done = Treatment.ownership_objects.get_queryset_for_user(user).filter(finish_date__isnull=False)
    if date_from:
        done = done.filter(finish_date__gte=date_from)
    if date_to:
        done = done.filter(finish_date__lte=date_to)
    base = list(last_per_field(done, COLOR_BASE))

    fields = all_fields
    if f['field']:
        fields = [x for x in all_fields if str(x.id) in f['field']]
    if any(f.values()):
        treatments = done
        if f['field']:
            treatments = treatments.filter(field_id__in=f['field'])
        if f['type']:
            treatments = treatments.filter(type__in=f['type'])
        if f['product_types']:
            treatments = treatments.filter(id__in=TreatmentProduct.objects.filter(
                product__product_type_id__in=f['product_types']).values('treatment_id'))
        if f['products']:
            treatments = treatments.filter(id__in=TreatmentProduct.objects.filter(
                product_id__in=f['products']).values('treatment_id'))
        treatments = list(last_per_field(treatments, limit))
    else:
        treatments = [t for t in base if t.rank <= limit]  # sin filtros, lo visible sale de la base

    # Parecidos → color. Los nombres de parcela no cuentan como parecido («ARAÑA CARTUJA»).
    pool = {t.id: t for t in base}
    for t in treatments:
        pool.setdefault(t.id, t)
    shown = {t.id: t for t in treatments}
    excluded = {fl.name for fl in all_fields}
    all_groups = group_similar(
        [(t.id, t.name, {tp.product_id for tp in t.treatmentproduct_set.all()})
         for t in sorted(pool.values(), key=lambda t: t.id)],
        excluded_words=excluded,
    )
    groups = []
    for index, group in enumerate(all_groups):
        visible = [k for k in group['keys'] if k in shown]
        if len(visible) < 2:  # «parecido» a algo que no se ve no aporta: sin color
            continue
        groups.append({'color': index % COLORS, 'dashed': index >= COLORS,
                       'count': len(visible), 'keys': visible})
    # La etiqueta, con lo que se ve; la leyenda, por lo que más se ve (el color no cambia)
    for group, label in zip(groups, label_groups([[shown[k].name for k in g['keys']] for g in groups],
                                                 excluded)):
        group['label'] = label
    groups.sort(key=lambda g: (-g['count'], g['color'], g['dashed']))
    group_of = {}
    for i, group in enumerate(groups, start=1):
        group['index'] = i  # data-bf-group de leyenda y tarjetas
        for key in group['keys']:
            group_of[key] = group

    by_field = {}
    for t in treatments:
        t.similar = group_of.get(t.id)
        by_field.setdefault(t.field_id, []).append(t)

    rows = [
        {'field': field, 'treatments': by_field.get(field.id, []),
         'missing': range(limit - len(by_field.get(field.id, [])))}
        for field in fields
    ]
    return {'rows': rows, 'groups': groups, 'has_treatments': bool(treatments),
            'limit': limit, 'columns': range(1, limit + 1)}
