from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cs_analyze",
    broker=settings.redis_broker_url,
    backend=settings.redis_result_url,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
    # A Scout holds its slot for up to an hour; the Review refresh gets the other
    # thread instead of waiting behind it (the worker runs `-Q celery,light`).
    task_routes={"cs_analyze.refresh_reviews": {"queue": settings.celery_light_queue}},
)
