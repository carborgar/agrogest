# Resumen: Protección de cuota AEMET en Vercel

## Problema identificado
- Token AEMET único para toda la app (40 req/min es el límite oficial)
- Vercel usa lambdas stateless: cada instancia tiene caché local desconectada
- Riesgo: cada lambda suma su contador independiente → podría superarse el límite global fácilmente

## Solución implementada

### 1. Caché en Base de Datos (compartida entre lambdas)
**Archivo**: `agrogest/settings.py`
- En producción/Vercel: `DatabaseCache` → tabla `agrogest_cache` en la BD
- En desarrollo local: `LocMemCache` (en memoria del proceso, sin necesidad de BD extra)
- Configurable por variable de entorno: `DJANGO_CACHE_BACKEND`

### 2. Limitador global por minuto de peticiones a AEMET
**Archivo**: `farm/weather_service.py`
- Contador compartido en caché usando ventana UTC de 60s
- Límite interno: 30 req/min (margen de seguridad bajo los 40 oficiales)
- Si se alcanza el límite, devuelve dato cacheado "stale" en lugar de fallar
- Configurable: `AEMET_RATE_LIMIT_PER_MINUTE`

### 3. Cachés de previsión por municipio
**Archivo**: `farm/weather_service.py`
- **Fresca**: TTL 30 min (1800s) → evita llamadas repetidas frecuentes
- **Stale (respaldo)**: TTL 6h (21600s) → fallback si hay rate-limit o fallo temporal
- Claves en caché: `aemet_weather_muni:{cod}`, `aemet_weather_muni_stale:{cod}`

### 4. Blindaje de operaciones de caché
**Archivo**: `farm/weather_service.py`
- Wrappers seguros `_cache_*_safe()` que no crashean si BD de caché no existe
- Logging de advertencias sin lanzar excepciones
- Diseño "fail-open": si caché falla, el servicio sigue respondiendo (aunque sin límite)

### 5. Setup automático en Vercel
**Archivo**: `entrypoint.sh`
```bash
createcachetable agrogest_cache  # crea tabla de caché
check_cache_health                # verifica que funcione
migrate --noinput                 # migraciones de BD
```

### 6. Comando de verificación
**Archivo**: `farm/management/commands/check_cache_health.py`
- Test SET, GET, DELETE de caché
- Util para diagnosticar problemas en Vercel sin deploying
- Ejecutable: `python manage.py check_cache_health`

## Archivos modificados/creados
```
agrogest/settings.py
├── CACHES configurable por entorno
├── AEMET_RATE_LIMIT_PER_MINUTE (default 30)
├── AEMET_WEATHER_CACHE_TTL (default 1800s)
└── AEMET_WEATHER_STALE_TTL (default 21600s)

entrypoint.sh
├── createcachetable (antes de migrate)
└── check_cache_health (verificación de salud)

farm/weather_service.py
├── _allow_aemet_request() (limitador global)
├── _cache_*_safe() (wrappers a prueba de fallos)
├── AemetRateLimitExceeded (excepción interna)
└── get_weather_for_field() (cachés fresca+stale)

farm/management/commands/check_cache_health.py
└── Comando para verificar caché funciona

VERCEL_CACHE_DEPLOYMENT.md
└── Guía de troubleshooting y configuración
```

## Comportamiento en Vercel
1. **Deploy**: entrypoint.sh crea tabla de caché + verifica salud
2. **Lambda 1**: request a AEMET → contador=1, guarda datos en caché
3. **Lambda 2**: request a AEMET → lee contador global de BD (=1), suma a 2
4. **Lambda N**: si contador > 30 → devuelve dato stale sin llamar a AEMET
5. **Cada minuto**: reinicia el contador (ventana UTC)

## Fallback si caché falla
Si la tabla `agrogest_cache` no existe o hay error en BD:
- Wrappers log warning pero no fallan
- Lambda puede seguir respondiendo (sin protección de límite)
- Conviene revisar logs y hacer `python manage.py createcachetable` manualmente

## Tests
- `farm/tests/test_weather_service_cache_and_limits.py` (3 tests de caché+límite)
- `farm/tests/test_management_commands.py` (1 test de health check)

## Próximos pasos opcionales
- Limitar concurrencia de peticiones desde frontend (pool de 3-4 simultáneas)
- Añadir métricas de consumo AEMET a Sentry
- Configurar alertas si se alcanza 80% del límite

