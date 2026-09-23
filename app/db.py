"""Conexion a MongoDB e indices del modelo de lectura."""

import logging

from pymongo import ASCENDING, DESCENDING, MongoClient

from .config import settings

logger = logging.getLogger(__name__)

client = MongoClient(
    settings.mongo_url,
    serverSelectionTimeoutMS=5_000,
    tz_aware=True,
    appname="kubo-analytics",
)

database = client[settings.mongo_db]

# Bitacora cruda de eventos (deduplicacion por _id = event_id).
events_collection = database["events"]

# Proyeccion de ventas lista para consultar (una fila por venta).
sales_collection = database["sales"]


def ensure_indexes() -> None:
    """Crea los indices necesarios. Es idempotente."""
    events_collection.create_index([("event_type", ASCENDING)])
    events_collection.create_index([("received_at", DESCENDING)])

    sales_collection.create_index([("sale_id", ASCENDING)], unique=True)
    sales_collection.create_index([("tenant_id", ASCENDING), ("sold_at", DESCENDING)])
    sales_collection.create_index([("tenant_id", ASCENDING), ("status", ASCENDING)])
    sales_collection.create_index([("tenant_id", ASCENDING), ("items.product_name", ASCENDING)])

    logger.info("indices de MongoDB verificados")


def ping() -> bool:
    """Comprueba que MongoDB responde."""
    try:
        client.admin.command("ping")
        return True
    except Exception as error:  # noqa: BLE001 - se reporta como estado degradado
        logger.warning("MongoDB no responde: %s", error)
        return False
