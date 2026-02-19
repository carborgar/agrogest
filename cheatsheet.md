# AgroGest - Comandos de build antes de hacer push

Antes de cada `git push`, ejecutar en orden:

## 1. Compilar SCSS
```bash
npx sass scss/custom-bootstrap.scss static/css/custom-bootstrap.min.css --style=compressed
```

## 2. Recopilar estáticos
```bash
python3 manage.py collectstatic --noinput
```

## 3. Commitear los assets generados
```bash
git add staticfiles static/css/custom-bootstrap.min.css
git commit -m "build assets"
git push
```

---

> Las migraciones se ejecutan automáticamente al arrancar la app en Vercel (via `wsgi.py`), no hace falta hacerlas manualmente.