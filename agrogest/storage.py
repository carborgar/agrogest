"""
Storage backends personalizados para AgroGest.
"""

import logging

from storages.backends.s3boto3 import S3ManifestStaticStorage

logger = logging.getLogger(__name__)


class IncrementalS3ManifestStaticStorage(S3ManifestStaticStorage):
    """
    Extensión de S3ManifestStaticStorage que precarga la lista completa de
    objetos existentes en R2/S3 con UNA SOLA llamada list_objects_v2, en lugar
    de emitir una petición HEAD individual por cada fichero.

    Con 200+ ficheros esto reduce el tiempo de collectstatic de minutos a
    segundos cuando la mayoría de estáticos ya están subidos.

    Comportamiento:
      - Primera vez (bucket vacío): igual que S3ManifestStaticStorage.
      - Siguientes ejecuciones: sólo sube los ficheros nuevos o modificados
        (cuyo nombre hashed será distinto), el resto se omite.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._existing_keys: set | None = None  # None = todavía no precargado

    # ------------------------------------------------------------------
    # Precarga
    # ------------------------------------------------------------------

    def _preload_existing_keys(self) -> None:
        """Lista todos los objetos del bucket/prefix con paginación."""
        prefix = (self.location or "").rstrip("/")
        if prefix:
            prefix += "/"

        client = self.connection.meta.client
        paginator = client.get_paginator("list_objects_v2")

        existing: set[str] = set()
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                existing.add(obj["Key"])

        logger.info(
            "[IncrementalStorage] Precarga completada: %d objetos en R2 (prefix='%s')",
            len(existing),
            prefix,
        )
        self._existing_keys = existing

    # ------------------------------------------------------------------
    # Override de exists() — usa la caché en memoria en lugar de HEAD
    # ------------------------------------------------------------------

    def exists(self, name: str) -> bool:
        # Caso borde: nombre vacío → deja que el padre gestione (comprueba el bucket)
        if not name:
            return super().exists(name)

        if self._existing_keys is None:
            self._preload_existing_keys()

        key = self._normalize_name(self._clean_name(name))
        return key in self._existing_keys

    # ------------------------------------------------------------------
    # Override de _save() — actualiza la caché tras subir un fichero nuevo
    # ------------------------------------------------------------------

    def _save(self, name: str, content) -> str:
        result = super()._save(name, content)
        # Añade el fichero recién subido a la caché para evitar dobles subidas
        # dentro de la misma ejecución de collectstatic
        if self._existing_keys is not None:
            key = self._normalize_name(self._clean_name(result))
            self._existing_keys.add(key)
        return result

