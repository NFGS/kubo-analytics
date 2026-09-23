"""Pruebas de las utilidades de conversion (sin MongoDB ni RabbitMQ)."""

from datetime import datetime, timezone

from app.processing import normalize_items, parse_datetime, to_float, to_int


def test_to_float_acepta_strings_decimales_del_evento():
    assert to_float("11900.00") == 11900.0
    assert to_float("0") == 0.0
    assert to_float(None) == 0.0
    assert to_float("no-numerico") == 0.0
    assert to_float(True) == 0.0


def test_to_int_ignora_booleanos_y_convierte_cadenas():
    assert to_int("3") == 3
    assert to_int(3.9) == 3
    assert to_int(None) == 0
    assert to_int(False) == 0


def test_parse_datetime_interpreta_iso8601_y_es_tolerante():
    parsed = parse_datetime("2026-09-23T15:30:00Z")
    assert parsed.tzinfo is not None
    assert parsed.year == 2026

    fallback = parse_datetime("texto invalido")
    assert fallback.tzinfo is not None
    assert isinstance(fallback, datetime)


def test_normalize_items_descarta_entradas_invalidas():
    items = normalize_items(
        [
            {"product_name": "Cafe", "quantity": "2", "unit_price": "5000.00", "total": "10000.00"},
            "basura",
            None,
        ]
    )

    assert len(items) == 1
    assert items[0]["product_name"] == "Cafe"
    assert items[0]["quantity"] == 2
    assert items[0]["total"] == 10000.0


def test_normalize_items_sin_lista_devuelve_vacio():
    assert normalize_items(None) == []
    assert normalize_items({"no": "es lista"}) == []


def test_fechas_se_normalizan_a_utc():
    naive = datetime(2026, 9, 23, 10, 0, 0)
    parsed = parse_datetime(naive)
    assert parsed.tzinfo == timezone.utc
