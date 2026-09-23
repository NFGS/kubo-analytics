"""Configuracion del servicio, leida del entorno."""

import os


class Settings:
    """Parametros de ejecucion. Todo llega por variables de entorno."""

    def __init__(self) -> None:
        self.mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27018")
        self.mongo_db: str = os.getenv("MONGO_DB", "kubo_analytics")
        self.amqp_url: str = os.getenv("AMQP_URL", "")
        self.port: int = int(os.getenv("PORT", "8084"))
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.exchange: str = "kubo.events"
        self.queue: str = "kubo.analytics.sale_created"
        self.dead_letter_queue: str = "kubo.analytics.sale_created.dlq"
        self.routing_keys: tuple[str, ...] = ("sale.created",)
        self.prefetch: int = 20
        self.reconnect_seconds: int = 10


settings = Settings()
