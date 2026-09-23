"""Consumidor de RabbitMQ.

Corre en un hilo aparte para no bloquear el bucle de eventos de FastAPI. Si el
bus no esta disponible, reintenta cada pocos segundos sin afectar a la API: el
tablero sigue respondiendo con lo que ya esta proyectado en MongoDB.

Los mensajes que fallan se envian a una cola de mensajes muertos (DLQ) en lugar
de perderse o bloquear la cola principal.
"""

import json
import logging
import threading
import time

import pika

from .config import settings
from .projection import process_event

logger = logging.getLogger(__name__)

_state = {"connected": False, "processed": 0, "duplicates": 0, "failed": 0}


def state() -> dict:
    """Estado del consumidor, expuesto en la sonda de salud."""
    return dict(_state)


def start_consumer_thread() -> threading.Thread | None:
    if not settings.amqp_url:
        logger.info("consumidor deshabilitado: AMQP_URL no configurada")
        return None

    thread = threading.Thread(target=_run_forever, name="amqp-consumer", daemon=True)
    thread.start()
    return thread


def _run_forever() -> None:
    while True:
        try:
            _consume()
        except Exception as error:  # noqa: BLE001 - el hilo nunca debe morir
            _state["connected"] = False
            logger.warning("consumidor caido (%s); reintento en %s s", error, settings.reconnect_seconds)
            time.sleep(settings.reconnect_seconds)


def _consume() -> None:
    parameters = pika.URLParameters(settings.amqp_url)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(exchange=settings.exchange, exchange_type="topic", durable=True)

    channel.queue_declare(queue=settings.dead_letter_queue, durable=True)
    channel.queue_declare(
        queue=settings.queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": settings.dead_letter_queue,
        },
    )

    for routing_key in settings.routing_keys:
        channel.queue_bind(
            queue=settings.queue, exchange=settings.exchange, routing_key=routing_key
        )

    channel.basic_qos(prefetch_count=settings.prefetch)
    channel.basic_consume(queue=settings.queue, on_message_callback=_on_message)

    _state["connected"] = True
    logger.info(
        "consumidor escuchando cola=%s claves=%s", settings.queue, ",".join(settings.routing_keys)
    )
    channel.start_consuming()


def _on_message(channel, method, properties, body) -> None:  # noqa: ANN001 - firma de pika
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        logger.error("mensaje no es JSON valido; se envia a la DLQ")
        _state["failed"] += 1
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    try:
        outcome = process_event(event)
        if outcome == "processed":
            _state["processed"] += 1
        elif outcome == "duplicate":
            _state["duplicates"] += 1
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as error:  # noqa: BLE001 - se registra y se manda a la DLQ
        logger.exception("fallo al procesar el evento: %s", error)
        _state["failed"] += 1
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
