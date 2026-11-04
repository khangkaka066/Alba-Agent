from typing import Any, Callable


class TTLCache:
    def __init__(self, capacity: int, ttl: float, clock: Callable[[], float]) -> None:
        raise NotImplementedError

    def set(self, key: Any, value: Any, ttl: float | None = None) -> None:
        raise NotImplementedError

    def get(self, key: Any, default: Any = None) -> Any:
        raise NotImplementedError

    def peek(self, key: Any, default: Any = None) -> Any:
        raise NotImplementedError

    def delete(self, key: Any) -> bool:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def __contains__(self, key: Any) -> bool:
        raise NotImplementedError

    def keys(self) -> list:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError
