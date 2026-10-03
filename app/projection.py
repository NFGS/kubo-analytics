"""Procesamiento idempotente de eventos de dominio."""

import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from .db import events_collection, sales_collection
from .processing import normalize_items, parse_datetime, to_float

logger = logging.getLogger(__name__)

PROCESSED = "processed"
DUPLICATE = "duplicate"
IGNORED = "ignored"


def process_event(event: dict) -> str:
    """
    Registra el evento y actualiza el modelo de lectura.

    La deduplicacion se apoya en el indice unico de `events._id = event_id`: si el
    mismo evento llega dos veces (reintento del publicador, reentrega del broker),
    la segunda insercion falla y el evento se descarta sin efectos.
    """
    event_id = event.get("event_id")
    event_type = event.get("event_type")

    if not event_id or not event_type:
        logger.warning("evento sin event_id o event_type: se ignora")
        return IGNORED

    try:
        events_collection.insert_one(
            {
                "_id": event_id,
                "event_type": event_type,
                "version": event.get("version"),
                "tenant_id": event.get("tenant_id"),
                "occurred_at": parse_datetime(event.get("occurred_at")),
                "payload": event,
                "received_at": datetime.now(timezone.utc),
            }
        )
    except DuplicateKeyError:
        logger.info("evento duplicado descartado id=%s", event_id)
        return DUPLICATE

    if event_type == "sale.created":
        _project_sale(event)
        logger.info("venta proyectada id=%s", event.get("data", {}).get("sale_id"))
        return PROCESSED

    logger.info("evento sin proyeccion asociada: %s", event_type)
    return IGNORED


def _project_sale(event: dict) -> None:
    data = event.get("data") or {}
    now = datetime.now(timezone.utc)

    sales_collection.update_one(
        # El filtro incluye el negocio: una reentrega no puede reescribir la
        # venta de otro negocio aunque compartiera el sale_id (defensa en
        # profundidad; el id ya es unico).
        {"sale_id": data.get("sale_id"), "tenant_id": event.get("tenant_id")},
        {
            "$set": {
                "sale_id": data.get("sale_id"),
                "tenant_id": event.get("tenant_id"),
                "number": data.get("number"),
                "status": data.get("status") or "COMPLETED",
                "customer_id": data.get("customer_id"),
                "customer_name": data.get("customer_name") or "Consumidor final",
                "payment_method": data.get("payment_method") or "CASH",
                "subtotal": to_float(data.get("subtotal")),
                "tax": to_float(data.get("tax")),
                "total": to_float(data.get("total")),
                "items": normalize_items(data.get("items")),
                "sold_at": parse_datetime(data.get("sold_at") or event.get("occurred_at")),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
