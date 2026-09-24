"""Pruebas de integracion con MongoDB real (P-08).

Levantan un contenedor de MongoDB y verifican lo que las pruebas puras no
pueden: que la deduplicacion por indice unico y la proyeccion de la venta
funcionen contra el motor.

Se omiten cuando no hay Docker disponible (por ejemplo, en un runner de CI sin
demonio), de modo que la suite unitaria sigue corriendo en cualquier entorno.
"""

import os
import shutil
from pathlib import Path

import pytest


def _docker_disponible() -> bool:
    """Docker accesible y la libreria de testcontainers instalada.

    Basta el socket (o `DOCKER_HOST`): el CLI no es necesario, testcontainers
    habla con el demonio directamente. Exigir el binario `docker` obligaba a
    saltar estas pruebas en contenedores con el socket montado.
    """
    try:
        import testcontainers.mongodb  # noqa: F401
    except ImportError:
        return False

    if shutil.which("docker") is not None:
        return True

    return Path("/var/run/docker.sock").exists() or bool(os.environ.get("DOCKER_HOST"))


pytestmark = pytest.mark.skipif(
    not _docker_disponible(), reason="requiere Docker y testcontainers"
)


@pytest.fixture(scope="module")
def collections():
    from pymongo import MongoClient
    from testcontainers.mongodb import MongoDbContainer

    with MongoDbContainer("mongo:8") as mongo:
        client = MongoClient(mongo.get_connection_url())
        database = client["kubo_analytics_test"]
        events = database["events"]
        sales = database["sales"]

        # Mismos indices que crea el servicio al arrancar.
        events.create_index([("event_type", 1)])
        sales.create_index([("sale_id", 1)], unique=True)

        yield events, sales
        client.close()


def _evento(sale_id: str = "venta-1", event_id: str = "evento-1") -> dict:
    return {
        "event_id": event_id,
        "event_type": "sale.created",
        "version": 1,
        "tenant_id": "negocio-1",
        "occurred_at": "2026-09-24T12:00:00Z",
        "data": {
            "sale_id": sale_id,
            "number": "V-000001",
            "status": "COMPLETED",
            "payment_method": "CASH",
            "subtotal": "10000.00",
            "tax": "1900.00",
            "total": "11900.00",
            "sold_at": "2026-09-24T12:00:00Z",
            "items": [
                {
                    "product_id": "producto-1",
                    "product_name": "Cafe",
                    "quantity": 1,
                    "unit_price": "11900.00",
                    "tax_rate": "19.00",
                    "tax_amount": "1900.00",
                    "total": "11900.00",
                }
            ],
        },
    }


def test_la_proyeccion_es_idempotente(collections, monkeypatch):
    events, sales = collections
    import app.projection as projection

    monkeypatch.setattr(projection, "events_collection", events)
    monkeypatch.setattr(projection, "sales_collection", sales)

    assert projection.process_event(_evento()) == "processed"
    # La reentrega del mismo evento no debe contar la venta dos veces.
    assert projection.process_event(_evento()) == "duplicate"

    assert events.count_documents({}) == 1
    assert sales.count_documents({"sale_id": "venta-1"}) == 1

    projected = sales.find_one({"sale_id": "venta-1"})
    assert projected["total"] == 11900.0
    assert projected["items"][0]["product_name"] == "Cafe"


def test_un_evento_sin_sobre_se_ignora(collections, monkeypatch):
    events, sales = collections
    import app.projection as projection

    monkeypatch.setattr(projection, "events_collection", events)
    monkeypatch.setattr(projection, "sales_collection", sales)

    # La coleccion es compartida por el modulo: se compara contra el estado previo.
    antes = events.count_documents({})
    assert projection.process_event({"data": {}}) == "ignored"
    assert events.count_documents({}) == antes
