"""
Agrupa tratamientos parecidos para pintarlos del mismo color en «Por parcela».

No clasifica tandas (la app no sabe qué es «la de la araña»): solo compara cada par por
  - productos en común, pesando menos los que van en casi todo (corrector de pH, mojante…),
  - nombre parecido, sin exigir que sea igual: se quitan tildes, números, palabras cortas y
    los nombres de las parcelas («ARAÑA 3 cartuja» ≈ «ARAÑA BORBOLI»), y las palabras casan
    aunque una sea el principio de la otra o tenga una errata.
y junta los que se parecen de media por encima de un umbral (enlace medio: evita que un
tratamiento mixto, p. ej. fungicida + insecticida, encadene dos grupos distintos).

Con la mezcla 50/50 y el umbral en 0,45 basta con que coincida del todo una de las dos cosas
(mismo nombre con productos rotados, como se hace con los acaricidas, o la misma receta con
otro nombre); si solo se parecen a medias, tienen que parecerse en ambas.
"""
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from difflib import SequenceMatcher

THRESHOLD = 0.45         # parecido medio mínimo para juntar dos grupos (ver arriba)
PRODUCT_WEIGHT = 0.5     # peso de los productos frente al nombre cuando hay ambos
MIN_TOKEN = 3
STOPWORDS = frozenset({'del', 'las', 'los', 'para', 'con', 'sin', 'por', 'solo', 'una', 'uno'})


def _strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))


def _words(text):
    """Palabras normalizadas → forma original (para la etiqueta del grupo)."""
    out = {}
    for word in re.findall(r'[^\W\d_]+', text or ''):
        key = _strip_accents(word).lower()
        if len(key) >= MIN_TOKEN and key not in STOPWORDS:
            out.setdefault(key, word)
    return out


@lru_cache(maxsize=4096)
def _same_word(a, b):
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.8


def name_tokens(name, excluded=frozenset()):
    """Palabras significativas del nombre, sin las que nombran parcelas (`excluded`)."""
    return {w: orig for w, orig in _words(name).items()
            if not any(_same_word(w, e) for e in excluded)}


def name_similarity(a, b):
    """Parte de las palabras del nombre más corto que aparecen (aproximadas) en el otro."""
    if not a or not b:
        return None
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    hits = sum(1 for w in short if any(_same_word(w, o) for o in long_))
    return hits / len(short)


def product_similarity(a, b, weights):
    """Jaccard ponderado: los productos que van en casi todos los tratamientos casi no cuentan."""
    if not a or not b:
        return None
    # Los pesos son siempre > 0 (idf suavizado), así que la unión nunca suma 0
    return sum(weights[p] for p in a & b) / sum(weights[p] for p in a | b)


def _combine(prod, name):
    if prod is None and name is None:
        return 0.0
    if prod is None:
        return name
    if name is None:
        return prod
    return PRODUCT_WEIGHT * prod + (1 - PRODUCT_WEIGHT) * name


def group_similar(items, excluded_words=frozenset(), threshold=THRESHOLD):
    """
    `items`: lista de (clave, nombre, conjunto de productos). `excluded_words`: textos (p. ej. nombres de
    parcela) cuyas palabras no cuentan; la exclusión es aproximada, así que «Navelinos» también quita «navel».
    Devuelve [{'keys': [...], 'label': str}] con los grupos de 2 o más, del mayor al menor.
    """
    n = len(items)
    if n < 2:
        return []
    # Se trocean con la misma regla que los nombres («Las Pitas», «Cartuja-2»)
    excluded = frozenset(w for text in excluded_words for w in _words(text))
    tokens = [name_tokens(name, excluded) for _, name, _ in items]
    products = [frozenset(p) for _, _, p in items]

    # Peso de cada producto según en cuántos tratamientos aparece (idf suavizado)
    df = Counter(p for ps in products for p in ps)
    weights = {p: math.log((n + 1) / (c + 0.5)) for p, c in df.items()}

    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            s = _combine(product_similarity(products[i], products[j], weights),
                         name_similarity(tokens[i], tokens[j]))
            sim[i][j] = sim[j][i] = s

    # Clustering aglomerativo con enlace medio. Se guarda la similitud media entre grupos y,
    # al fusionar a y b, se actualiza con Lance-Williams: s(k, a∪b) = (|a|·s(k,a) + |b|·s(k,b)) / (|a|+|b|).
    clusters = {i: [i] for i in range(n)}
    link = {i: {j: sim[i][j] for j in range(n) if j != i} for i in range(n)}

    def nearest(k):
        row = link[k]
        if not row:
            return (-1.0, None)
        other = max(row, key=lambda j: (row[j], -j))
        return (row[other], other)

    best = {k: nearest(k) for k in link}  # vecino más parecido de cada grupo (evita recorrer todos los pares)
    while len(clusters) > 1:
        a = max(best, key=lambda k: (best[k][0], -k))
        value, b = best[a]
        if b is None or value < threshold:
            break
        size_a, size_b = len(clusters[a]), len(clusters[b])
        del link[a][b]
        del link[b]
        del best[b]
        for k in link:
            if k == a:
                continue
            merged = (size_a * link[a][k] + size_b * link[k].pop(b)) / (size_a + size_b)
            link[a][k] = link[k][a] = merged
        clusters[a] += clusters.pop(b)
        for k in link:
            if k == a or best[k][1] in (a, b):
                best[k] = nearest(k)
            elif link[k][a] > best[k][0]:
                best[k] = (link[k][a], a)
    clusters = list(clusters.values())

    groups = []
    for members in clusters:
        if len(members) < 2:
            continue
        member_tokens = [tokens[i] for i in members]
        groups.append({
            'keys': [items[i][0] for i in members],
            'label': _label(member_tokens, [items[i][1] for i in members]),
            '_tokens': member_tokens,
        })
    groups.sort(key=lambda g: -len(g['keys']))
    _disambiguate(groups)
    return groups


def _disambiguate(groups):
    """Etiquetas únicas y nunca vacías. Si dos grupos se llaman igual («ARAÑA»), se añade la siguiente
    palabra de cada uno solo si la llevan al menos la mitad de sus tratamientos («ARAÑA LEANRI»);
    si no, o si aún coinciden, un número."""
    by_label = {}
    for g in groups:
        by_label.setdefault(g['label'] or 'Grupo', []).append(g)
    for label, same in by_label.items():
        if len(same) == 1:
            same[0]['label'] = label
            continue
        base = _strip_accents(label).lower().split()
        for g in same:
            word, c, orig = _top_word(g['_tokens'], exclude=base)
            g['label'] = f'{label} {orig}' if word and c * 2 >= len(g['_tokens']) else label
    seen = Counter()
    for g in groups:
        seen[g['label']] += 1
        if seen[g['label']] > 1 or sum(1 for o in groups if o['label'] == g['label']) > 1:
            g['label'] = f"{g['label']} ({seen[g['label']]})"
    for g in groups:
        del g['_tokens']


def _top_word(member_tokens, exclude=()):
    """(palabra, en cuántos aparece, forma original más frecuente) de la palabra más repetida."""
    counts, forms = Counter(), {}
    for toks in member_tokens:
        for w, orig in toks.items():
            if any(_same_word(w, e) for e in exclude):
                continue
            counts[w] += 1
            forms.setdefault(w, Counter())[orig] += 1
    if not counts:
        return None, 0, ''
    word, c = counts.most_common(1)[0]
    return word, c, forms[word].most_common(1)[0][0]


def _label(member_tokens, names):
    """La palabra que más se repite en el grupo («ARAÑA»); si ninguna domina, el nombre más repetido."""
    word, c, orig = _top_word(member_tokens)
    if word and c * 2 >= len(member_tokens):
        return orig
    return Counter(n.strip() for n in names).most_common(1)[0][0]
