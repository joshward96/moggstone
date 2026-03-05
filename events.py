from __future__ import annotations
from enum import Enum
from typing import Callable, Any


class EventType(str, Enum):
    ON_PLAY = "on_play"
    ON_DEATH = "on_death"
    ON_DAMAGE = "on_damage"
    ON_ATTACK = "on_attack"
    ON_TURN_START = "on_turn_start"
    ON_TURN_END = "on_turn_end"
    ON_DRAW = "on_draw"


class EventBus:
    """Simple publish/subscribe event bus. Handlers are keyed by (event_type, owner_id)."""

    def __init__(self):
        # List of (event_type, owner_id, handler_fn)
        self._handlers: list[tuple[EventType, str, Callable]] = []

    def subscribe(self, event_type: EventType, owner_id: str, handler: Callable) -> None:
        self._handlers.append((event_type, owner_id, handler))

    def unsubscribe_owner(self, owner_id: str) -> None:
        """Remove all handlers belonging to a given owner (e.g. a dying creature)."""
        self._handlers = [(et, oid, h) for et, oid, h in self._handlers if oid != owner_id]

    def dispatch(self, event_type: EventType, *args: Any) -> list[Any]:
        results = []
        # Iterate over a snapshot in case handlers modify the list
        for et, _oid, handler in list(self._handlers):
            if et == event_type:
                result = handler(*args)
                if result is not None:
                    results.append(result)
        return results

    def clear(self) -> None:
        self._handlers = []
