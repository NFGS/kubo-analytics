# kubo-analytics

Servicio de analítica de Kubo: consume los eventos del negocio, construye un
modelo de lectura en MongoDB y expone el tablero de indicadores.

| Campo | Valor |
| --- | --- |
| Stack | Python 3.13 · FastAPI · PyMongo · Pika |
| Base de datos | MongoDB 8 (`kubo_analytics`) |
| Puerto | 8084 (contenedor) · 9084 (host) |
| Ruta base | `/api/v1` |

## Por qué Python y MongoDB aquí

Los indicadores son agregaciones sobre documentos que cambian de forma
(productos por venta, clientes, métodos de pago). Un motor de agregación sobre
documentos resuelve el `$unwind` + `$group` sin esquema rígido ni migraciones, y
Python aporta el ecosistema para extender el tablero a pronóstico de demanda.

## Flujo de datos

```
kubo-erp ──sale.created──▶ RabbitMQ ──▶ consumidor (idempotente) ──▶ MongoDB
                                                                    ├── events (bitácora)
                                                                    └── sales  (proyección)
                                                                            │
                                                              GET /dashboard/* ──▶ PWA
```

## Endpoints

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/api/v1/health` | Estado del servicio, Mongo y consumidor |
| POST | `/api/v1/events` | Vía de respaldo para reenviar eventos por HTTP |
| GET | `/api/v1/dashboard/summary` | Ventas, ingreso, ticket promedio, unidades, hoy |
| GET | `/api/v1/dashboard/sales-by-day` | Serie diaria (`days`) |
| GET | `/api/v1/dashboard/top-products` | Productos más vendidos (`limit`) |
| GET | `/api/v1/dashboard/top-customers` | Mejores clientes (`limit`) |
| GET | `/api/v1/dashboard/payment-methods` | Distribución por medio de pago |
| GET | `/api/v1/dashboard/recent-sales` | Últimas ventas (`limit`) |
| GET | `/api/v1/dashboard/rotation` | Productos con más salida en 7 días |

## Idempotencia

`events._id` es el `event_id` del evento y tiene índice único. Si el mismo evento
llega dos veces (reintento del publicador o reentrega del broker), la segunda
inserción falla con `DuplicateKeyError` y el evento se descarta sin efectos: la
proyección nunca cuenta una venta dos veces.

## Tolerancia a fallos

- Si RabbitMQ no responde, el consumidor reintenta cada 10 s en un hilo aparte;
  la API sigue respondiendo con lo ya proyectado.
- Los mensajes que no se pueden procesar se envían a la cola de mensajes muertos
  `kubo.analytics.sale_created.dlq` en lugar de perderse o bloquear la cola.
- `AMQP_URL` vacía deshabilita el consumidor (modo solo lectura).

## Precisión numérica

La contabilidad exacta vive en `kubo-erp` con aritmética decimal. Aquí los
importes se proyectan como punto flotante porque las agregaciones sobre miles de
documentos no requieren precisión de centavo y así se aprovechan los operadores
nativos de MongoDB. Es una decisión consciente, no un descuido: el tablero es
para decidir, la factura es para cobrar.

## Ejecución local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8084
```

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest -q
```
