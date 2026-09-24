"""Trazas OpenTelemetry de analitica (P-07).

Solo se activan cuando `OTEL_EXPORTER_OTLP_ENDPOINT` esta definido: sin
collector el servicio arranca igual. La instrumentacion de FastAPI cubre cada
peticion HTTP; el consumidor de eventos queda fuera por ahora (no es una
peticion y su trazado es un trabajo aparte).
"""

import logging
import os

logger = logging.getLogger("kubo-analytics")


def setup_tracing(app) -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({"service.name": "kubo-analytics"})
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("trazas OTLP activas hacia %s", endpoint)
    except Exception as error:  # la observabilidad nunca tumba el servicio
        logger.warning("no se pudo activar el trazado: %s", error)
