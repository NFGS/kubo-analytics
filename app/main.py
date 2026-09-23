"""API de analitica de Kubo: tablero, KPIs y bitacora de eventos."""

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from . import repository
from .config import settings
from .consumer import start_consumer_thread, state as consumer_state
from .db import ensure_indexes, ping
from .projection import process_event

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("kubo-analytics")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_indexes()
    start_consumer_thread()
    logger.info("kubo-analytics listo")
    yield
    logger.info("kubo-analytics detenido")


app = FastAPI(
    title="Kubo Analytics",
    version="0.1.0",
    description="Modelo de lectura y tablero de indicadores para PYMES.",
    lifespan=lifespan,
)

api = APIRouter(prefix="/api/v1")


def tenant_id(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")) -> str:
    """La identidad llega verificada desde el API Gateway."""
    if not x_tenant_id:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHENTICATED", "message": "La peticion no trae identidad verificada"},
        )
    return x_tenant_id


class EventIn(BaseModel):
    """Sobre de evento aceptado por la via HTTP (respaldo del bus)."""

    event_id: str
    event_type: str
    version: int | None = None
    occurred_at: str | None = None
    tenant_id: str | None = None
    data: dict | None = None


@api.get("/health", tags=["sistema"])
def health() -> dict:
    database = "UP" if ping() else "DOWN"
    return {
        "status": "UP" if database == "UP" else "DEGRADED",
        "service": "kubo-analytics",
        "db": database,
        "consumer": consumer_state(),
        "time": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


@api.post("/events", tags=["eventos"], status_code=202)
def ingest_event(event: EventIn, _tenant: str = Depends(tenant_id)) -> dict:
    """
    Via de respaldo para reenviar eventos por HTTP cuando el bus no esta
    disponible (recuperacion o carga inicial). La via normal es RabbitMQ.
    """
    outcome = process_event(event.model_dump())
    return {"status": outcome}


@api.get("/dashboard/summary", tags=["tablero"])
def dashboard_summary(tenant: str = Depends(tenant_id)) -> dict:
    return {"data": repository.summary(tenant)}


@api.get("/dashboard/sales-by-day", tags=["tablero"])
def dashboard_sales_by_day(
    days: int = Query(default=14, ge=1, le=90), tenant: str = Depends(tenant_id)
) -> dict:
    return {"data": repository.sales_by_day(tenant, days)}


@api.get("/dashboard/top-products", tags=["tablero"])
def dashboard_top_products(
    limit: int = Query(default=10, ge=1, le=50), tenant: str = Depends(tenant_id)
) -> dict:
    return {"data": repository.top_products(tenant, limit)}


@api.get("/dashboard/payment-methods", tags=["tablero"])
def dashboard_payment_methods(tenant: str = Depends(tenant_id)) -> dict:
    return {"data": repository.sales_by_payment_method(tenant)}


@api.get("/dashboard/top-customers", tags=["tablero"])
def dashboard_top_customers(
    limit: int = Query(default=10, ge=1, le=50), tenant: str = Depends(tenant_id)
) -> dict:
    return {"data": repository.top_customers(tenant, limit)}


@api.get("/dashboard/recent-sales", tags=["tablero"])
def dashboard_recent_sales(
    limit: int = Query(default=10, ge=1, le=50), tenant: str = Depends(tenant_id)
) -> dict:
    return {"data": repository.recent_sales(tenant, limit)}


@api.get("/dashboard/rotation", tags=["tablero"])
def dashboard_rotation(tenant: str = Depends(tenant_id)) -> dict:
    """Productos con mas salida en los ultimos 7 dias."""
    return {"data": repository.product_rotation(tenant)}


app.include_router(api)
