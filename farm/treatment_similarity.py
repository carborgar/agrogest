"""
Agrupa tratamientos parecidos para pintarlos del mismo color en «Por parcela».

No clasifica tandas (la app no sabe qué es «la de la araña»): solo compara cada par por
  - productos en común, pesando menos los que van en casi todo (corrector de pH, mojante…),
  - nombre parecido, sin exigir que sea igual: se quitan tildes, números, palabras cortas y
    los nombres de las parcelas («ARAÑA 3 cartuja» ≈ «ARAÑA BORBOLI»), y las palabras casan
    aunque una sea el principio de la otra o tenga una errata.
y junta los que se parecen de media por encima de un umbral (enlace medio: evita que un
tratamiento mixto, p. ej. fungicida + insecticida, encadene dos grupos distintos).
"""
import math
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

THRESHOLD = 0.5          # parecido medio mínimo para juntar dos grupos
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
    union = sum(weights[p] for p in a | b)
    if union == 0:
        return 1.0 if a == b else 0.0
    return sum(weights[p] for p in a & b) / union


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
    `items`: lista de (clave, nombre, conjunto de productos).
    Devuelve [{'keys': [...], 'label': str}] con los grupos de 2 o más, del mayor al menor.
    """
    n = len(items)
    if n < 2:
        return []
    excluded = frozenset(_strip_accents(w).lower() for w in excluded_words)
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

    # Clustering aglomerativo con enlace medio (n es pequeño: parcelas × N ≤ unos cientos)
    clusters = [[i] for i in range(n)]
    while True:
        best, pair = threshold, None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                ca, cb = clusters[a], clusters[b]
                avg = sum(sim[i][j] for i in ca for j in cb) / (len(ca) * len(cb))
                if avg >= best:
                    best, pair = avg, (a, b)
        if pair is None:
            break
        a, b = pair
        clusters[a] = clusters[a] + clusters[b]
        del clusters[b]

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
    """Si dos grupos se llaman igual («ARAÑA»), se añade la siguiente palabra que más se repite en cada uno
    («ARAÑA LEANRI») y, si no hay, un número."""
    by_label = {}
    for g in groups:
        by_label.setdefault(g['label'], []).append(g)
    for label, same in by_label.items():
        if len(same) > 1:
            base = _strip_accents(label).lower()
            for n, g in enumerate(same, start=1):
                counts, original = Counter(), {}
                for toks in g['_tokens']:
                    for w, orig in toks.items():
                        if not _same_word(w, base) and w not in base.split():
                            counts[w] += 1
                            original.setdefault(w, orig)
                extra = original[counts.most_common(1)[0][0]] if counts else str(n)
                g['label'] = f'{label} {extra}'
    for g in groups:
        del g['_tokens']


def _label(member_tokens, names):
    """La palabra que más se repite en el grupo («ARAÑA»); si ninguna domina, el nombre más repetido."""
    counts, original = Counter(), {}
    for toks in member_tokens:
        for w, orig in toks.items():
            counts[w] += 1
            original.setdefault(w, orig)
    if counts:
        word, c = counts.most_common(1)[0]
        if c * 2 >= len(member_tokens):
            return original[word]
    return Counter(names).most_common(1)[0][0]
