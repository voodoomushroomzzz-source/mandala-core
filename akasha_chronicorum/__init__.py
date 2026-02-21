"""Akasha Chronicorum – хранилище событий и артефактов Мандалы."""
from .core import push_event, get_events, get_artifacts  # экспортируем нужное
__all__ = ["push_event", "get_events", "get_artifacts"]
