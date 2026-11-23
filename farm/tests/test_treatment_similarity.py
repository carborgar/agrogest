"""Agrupación de tratamientos parecidos (productos + nombre aproximado) para colorear «Por parcela»."""
from farm.treatment_similarity import group_similar, name_similarity, name_tokens

FIELDS = {'Cartuja', 'Borboli', 'Las', 'Pitas', 'Navelinos'}
PH, MOJ = 'rango', 'mojante'  # van en casi todo


def _groups(items):
    return [sorted(g['keys']) for g in group_similar(items, FIELDS)]


def test_name_ignores_accents_numbers_and_field_names():
    a = name_tokens('ARAÑA 3 cartuja', {'cartuja'})
    b = name_tokens('Araña BORBOLI', {'borboli'})
    assert set(a) == set(b) == {'arana'}
    assert name_similarity(a, b) == 1


def test_name_matches_prefixes_and_typos():
    assert name_similarity(name_tokens('Fungicida cobre'), name_tokens('COBRES')) == 1
    assert name_similarity(name_tokens('Phytophtora'), name_tokens('PHYTOPHTHORA')) == 1
    assert name_similarity(name_tokens('Cobre'), name_tokens('Cabrio')) == 0


def test_same_round_grouped_across_fields_even_with_different_names():
    items = [
        ('a1', 'ARAÑA CARTUJA', {PH, 'flash', 'nissorun'}),
        ('a2', 'ARAÑA BORBOLI', {PH, 'flash', 'nissorun', 'fulmit'}),
        ('a3', 'Araña 2', {PH, 'nissorun', 'apache'}),
        ('c1', 'COBRE', {'cuprocol'}),
        ('c2', 'COBRE', {'cuprocol'}),
        ('x', 'MOSCA', {MOJ, 'karate'}),
    ]
    assert _groups(items) == [['a1', 'a2', 'a3'], ['c1', 'c2']]


def test_common_products_alone_do_not_group():
    items = [(i, name, {PH, MOJ, own}) for i, (name, own) in
             enumerate([('Cobre', 'cuprocol'), ('Cabrio', 'cabrio'), ('Mosca', 'karate'), ('Calibre', 'nitrato')])]
    assert _groups(items) == []


def test_same_products_different_names_still_group():
    items = [('p1', 'Tratamiento hongo', {'alfil', 'sulfato'}), ('p2', 'PHYTOPHTHORA', {'alfil', 'sulfato'}),
             ('z', 'Otro', {'karate'})]
    assert _groups(items) == [['p1', 'p2']]


def test_mixed_treatment_does_not_chain_two_groups():
    items = [
        ('f1', 'CABRIO', {'cabrio'}), ('f2', 'CABRIO', {'cabrio'}),
        ('m', 'CABRIO + KARATE', {'cabrio', 'karate'}),
        ('i1', 'MOSCA', {'karate'}), ('i2', 'MOSCA', {'karate'}),
    ]
    groups = _groups(items)
    assert ['i1', 'i2'] in groups
    assert not any({'f1', 'i1'} <= set(g) for g in groups)


def test_labels_use_shared_word_and_disambiguate_duplicates():
    items = [
        ('a1', 'ARAÑA NADOR', {'flash', 'fulmit'}), ('a2', 'ARAÑA NADOR pitas', {'flash', 'fulmit'}),
        ('b1', 'ARAÑA LEANRI', {'citrol', 'apache'}), ('b2', 'ARAÑA LEANRI', {'citrol', 'apache'}),
    ]
    labels = sorted(g['label'] for g in group_similar(items, FIELDS, threshold=0.6))
    assert labels == ['ARAÑA LEANRI', 'ARAÑA NADOR']


def test_singletons_and_empty_input():
    assert group_similar([]) == []
    assert group_similar([('a', 'COBRE', {'c'})]) == []
