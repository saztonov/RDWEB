"""Тесты для конфигурации Celery."""

from app.celery_app import celery_app


def test_celery_broker_configured():
    """Celery broker URL должен быть задан."""
    assert celery_app.conf.broker_url is not None


def test_visibility_timeout():
    """visibility_timeout = 86400 (24h) для длинных OCR задач."""
    opts = celery_app.conf.broker_transport_options
    assert opts["visibility_timeout"] == 86400


def test_acks_late():
    """task_acks_late включён для надёжности."""
    assert celery_app.conf.task_acks_late is True


def test_reject_on_worker_lost_disabled():
    """reject_on_worker_lost выключен — zombie_detector восстанавливает задачи."""
    assert celery_app.conf.task_reject_on_worker_lost is False


def test_json_serialization():
    """Сериализация только JSON."""
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"


def test_priority_queue():
    """Приоритетная очередь настроена."""
    assert celery_app.conf.task_queue_max_priority == 10
