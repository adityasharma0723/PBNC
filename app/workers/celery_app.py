"""Celery application configuration.

Uses Redis as both broker and result backend. Task serialization uses JSON
for security (pickle deserialization is a known attack vector).
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "docintel",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # Re-deliver tasks if worker crashes
    worker_prefetch_multiplier=1,  # Fair scheduling across workers
)

# Auto-discover tasks in the workers package
celery_app.autodiscover_tasks(["app.workers"])
