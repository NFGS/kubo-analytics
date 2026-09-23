"""Utilidades de conversion para el modelo de lectura.

La contabilidad exacta vive en el ERP (aritmetica decimal). Analitica usa punto
flotante a proposito: las agregaciones sobre miles de documentos no necesitan
precision de centavo y MongoDB agrega numeros de forma nativa.
"""

from datetime import datetime, timezone


def to_float(value: object) -> float:
    """Convierte un importe (string decimal del evento) a float."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def to_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def parse_datetime(value: object) -> datetime:
    """Parsea el `occurred_at`/`sold_at` ISO-8601 del evento."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def normalize_items(items: object) -> list[dict]:
    """Normaliza el detalle de la venta para poder agregarlo con $unwind."""
    if not isinstance(items, list):
        return []

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "product_id": item.get("product_id"),
                "product_name": item.get("product_name") or "Sin nombre",
                "quantity": to_int(item.get("quantity")),
                "unit_price": to_float(item.get("unit_price")),
                "tax_amount": to_float(item.get("tax_amount")),
                "total": to_float(item.get("total")),
            }
        )
    return normalized
