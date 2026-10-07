# kubo-analytics
[!\[CI](https://github.com/NFGS/kubo-analytics/actions/workflows/ci.yml/badge.svg)\]([https://github.com/NFGS/kubo-analytics/actions/workflows/ci.yml](https://github.com/NFGS/kubo-analytics/actions/workflows/ci.yml))
> Parte del proyecto **Kubo** — [kubo-workspace](https://github.com/NFGS/kubo-workspace) (ERP + CRM autoalojable para PYMES).
Servicio de analítica de Kubo: consume los eventos del negocio, construye un
modelo de lectura en MongoDB y expone el tablero de indicadores.
<table header-row="true">
<tr>
<td>Campo</td>
<td>Valor</td>
</tr>
<tr>
<td>Stack</td>
<td>Python 3.13 · FastAPI · PyMongo · Pika</td>
</tr>
<tr>
<td>Base de datos</td>
<td>MongoDB 8 (`kubo_analytics`)</td>
</tr>
<tr>
<td>Puerto</td>
<td>8084 (contenedor) · 9084 (host)</td>
</tr>
<tr>
<td>Ruta base</td>
<td>`/api/v1`</td>
</tr>
</table>
## Por qué Python y MongoDB aquí
Los indicadores son agregaciones sobre documentos que cambian de forma
(productos por venta, clientes, métodos de pago). Un motor de agregación sobre
documentos resuelve el `$unwind` + `$group` sin esquema rígido ni migraciones, y
Python aporta el ecosistema para extender el tablero a pronóstico de demanda.
## Flujo de datos
```javascript
kubo-erp ──sale.created──▶ RabbitMQ ──▶ consumidor (idempotente) ──▶ MongoDB
                                                                    ├── events (bitácora)
                                                                    └── sales  (proyección)
                                                                            │
                                                              GET /dashboard/* ──▶ PWA
```
## Endpoints
<table header-row="true">
<tr>
<td>Método</td>
<td>Ruta</td>
<td>Descripción</td>
</tr>
<tr>
<td>GET</td>
<td>`/api/v1/health`</td>
<td>Estado del servicio, Mongo y consumidor</td>
</tr>
<tr>
<td>POST</td>
<td>`/api/v1/events`</td>
<td>Vía de respaldo para reenviar eventos por HTTP; el negocio lo impone la identidad verificada, no el cuerpo</td>
</tr>
<tr>
<td>GET</td>
<td>`/api/v1/dashboard/summary`</td>
<td>Ventas, ingreso, ticket promedio, unidades, hoy</td>
</tr>
<tr>
<td>GET</td>
<td>`/api/v1/dashboard/sales-by-day`</td>
<td>Serie diaria (`days`)</td>
</tr>
<tr>
<td>GET</td>
<td>`/api/v1/dashboard/top-products`</td>
<td>Productos más vendidos (`limit`)</td>
</tr>
<tr>
<td>GET</td>
<td>`/api/v1/dashboard/top-customers`</td>
<td>Mejores clientes (`limit`)</td>
</tr>
<tr>
<td>GET</td>
<td>`/api/v1/dashboard/payment-methods`</td>
<td>Distribución por medio de pago</td>
</tr>
<tr>
<td>GET</td>
<td>`/api/v1/dashboard/recent-sales`</td>
<td>Últimas ventas (`limit`)</td>
</tr>
<tr>
<td>GET</td>
<td>`/api/v1/dashboard/rotation`</td>
<td>Productos con más salida en 7 días</td>
</tr>
</table>
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
./kubo-infra/scripts/analytics-tests.sh
```
**8 pruebas**: 6 unitarias de conversión y 2 de integración con MongoDB real
(testcontainers, `mongo:8.2` como el compose) que verifican la deduplicación por
índice único y la proyección de la venta. La cobertura del módulo de dominio
(`app.processing`) se vigila con gate de **80 %**; hoy **93 %**.
## Observabilidad y calidad (Fase 2)
- **Trazas OpenTelemetry**: `app/tracing.py` instrumenta FastAPI y exporta OTLP
	solo si hay collector configurado.
- **Cobertura**: gate de **80 %** sobre el módulo de dominio (`app.processing`)
	con pytest-cov; hoy 93 %.
