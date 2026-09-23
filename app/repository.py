"""Consultas de tablero sobre el modelo de lectura de MongoDB."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings
from .db import sales_collection

# Zona horaria del negocio. Las fechas se guardan en UTC, pero el dia comercial
# se calcula aqui: una venta de las 20:00 en Colombia pertenece a ese dia.
BUSINESS_TZ = ZoneInfo(settings.timezone)


def _start_of_business_day(moment: datetime | None = None) -> datetime:
    """Medianoche del dia comercial, expresada en UTC para poder consultar."""
    local = (moment or datetime.now(timezone.utc)).astimezone(BUSINESS_TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _base_match(tenant_id: str, only_completed: bool = True) -> dict:
    match: dict = {"tenant_id": tenant_id}
    if only_completed:
        match["status"] = "COMPLETED"
    return {"$match": match}


def summary(tenant_id: str) -> dict:
    """Indicadores principales del negocio."""
    start_of_day = _start_of_business_day()

    totals = list(
        sales_collection.aggregate(
            [
                _base_match(tenant_id),
                {
                    "$group": {
                        "_id": None,
                        "sales_count": {"$sum": 1},
                        "revenue": {"$sum": "$total"},
                        "tax": {"$sum": "$tax"},
                        "avg_ticket": {"$avg": "$total"},
                        "units": {"$sum": {"$sum": "$items.quantity"}},
                    }
                },
            ]
        )
    )

    today = list(
        sales_collection.aggregate(
            [
                {
                    "$match": {
                        "tenant_id": tenant_id,
                        "status": "COMPLETED",
                        "sold_at": {"$gte": start_of_day},
                    }
                },
                {"$group": {"_id": None, "revenue": {"$sum": "$total"}, "sales_count": {"$sum": 1}}},
            ]
        )
    )

    customers = sales_collection.distinct(
        "customer_id", {"tenant_id": tenant_id, "status": "COMPLETED"}
    )

    row = totals[0] if totals else {}
    today_row = today[0] if today else {}

    return {
        "sales_count": row.get("sales_count", 0),
        "revenue": round(row.get("revenue", 0.0), 2),
        "tax": round(row.get("tax", 0.0), 2),
        "avg_ticket": round(row.get("avg_ticket", 0.0), 2),
        "units_sold": row.get("units", 0),
        "customers_count": len([customer for customer in customers if customer]),
        "today": {
            "revenue": round(today_row.get("revenue", 0.0), 2),
            "sales_count": today_row.get("sales_count", 0),
        },
    }


def sales_by_day(tenant_id: str, days: int = 14) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = sales_collection.aggregate(
        [
            {
                "$match": {
                    "tenant_id": tenant_id,
                    "status": "COMPLETED",
                    "sold_at": {"$gte": since},
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$sold_at",
                            "timezone": settings.timezone,
                        }
                    },
                    "revenue": {"$sum": "$total"},
                    "sales_count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
    )

    return [
        {"date": row["_id"], "revenue": round(row["revenue"], 2), "sales_count": row["sales_count"]}
        for row in rows
    ]


def top_products(tenant_id: str, limit: int = 10) -> list[dict]:
    rows = sales_collection.aggregate(
        [
            _base_match(tenant_id),
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": "$items.product_name",
                    "quantity": {"$sum": "$items.quantity"},
                    "revenue": {"$sum": "$items.total"},
                }
            },
            {"$sort": {"revenue": -1}},
            {"$limit": limit},
        ]
    )

    return [
        {
            "product_name": row["_id"],
            "quantity": row["quantity"],
            "revenue": round(row["revenue"], 2),
        }
        for row in rows
    ]


def sales_by_payment_method(tenant_id: str) -> list[dict]:
    rows = sales_collection.aggregate(
        [
            _base_match(tenant_id),
            {
                "$group": {
                    "_id": "$payment_method",
                    "revenue": {"$sum": "$total"},
                    "sales_count": {"$sum": 1},
                }
            },
            {"$sort": {"revenue": -1}},
        ]
    )

    return [
        {
            "payment_method": row["_id"],
            "revenue": round(row["revenue"], 2),
            "sales_count": row["sales_count"],
        }
        for row in rows
    ]


def top_customers(tenant_id: str, limit: int = 10) -> list[dict]:
    rows = sales_collection.aggregate(
        [
            _base_match(tenant_id),
            {"$match": {"customer_name": {"$nin": [None, ""]}}},
            {
                "$group": {
                    "_id": "$customer_name",
                    "revenue": {"$sum": "$total"},
                    "purchases": {"$sum": 1},
                    "last_purchase": {"$max": "$sold_at"},
                }
            },
            {"$sort": {"revenue": -1}},
            {"$limit": limit},
        ]
    )

    return [
        {
            "customer_name": row["_id"],
            "revenue": round(row["revenue"], 2),
            "purchases": row["purchases"],
            "last_purchase": row["last_purchase"].isoformat() if row.get("last_purchase") else None,
        }
        for row in rows
    ]


def recent_sales(tenant_id: str, limit: int = 10) -> list[dict]:
    rows = (
        sales_collection.find({"tenant_id": tenant_id}, {"_id": 0})
        .sort("sold_at", -1)
        .limit(limit)
    )

    return [
        {
            "sale_id": row.get("sale_id"),
            "number": row.get("number"),
            "customer_name": row.get("customer_name"),
            "total": round(row.get("total", 0.0), 2),
            "status": row.get("status"),
            "payment_method": row.get("payment_method"),
            "sold_at": row["sold_at"].isoformat() if row.get("sold_at") else None,
        }
        for row in rows
    ]


def low_stock_alerts(tenant_id: str) -> list[dict]:
    """Resumen de unidades vendidas por producto en los ultimos 7 dias."""
    since = datetime.now(timezone.utc) - timedelta(days=7)

    rows = sales_collection.aggregate(
        [
            {
                "$match": {
                    "tenant_id": tenant_id,
                    "status": "COMPLETED",
                    "sold_at": {"$gte": since},
                }
            },
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": "$items.product_name",
                    "quantity": {"$sum": "$items.quantity"},
                }
            },
            {"$sort": {"quantity": -1}},
            {"$limit": 10},
        ]
    )

    return [{"product_name": row["_id"], "quantity_7d": row["quantity"]} for row in rows]
