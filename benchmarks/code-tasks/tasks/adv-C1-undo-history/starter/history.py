from __future__ import annotations


class History:
    def __init__(self, initial, limit=None) -> None:
        raise NotImplementedError

    @property
    def current(self):
        raise NotImplementedError

    def commit(self, state) -> bool:
        raise NotImplementedError

    def undo(self):
        raise NotImplementedError

    def redo(self):
        raise NotImplementedError

    @property
    def can_undo(self) -> bool:
        raise NotImplementedError

    @property
    def can_redo(self) -> bool:
        raise NotImplementedError

    @property
    def undo_steps(self) -> int:
        raise NotImplementedError

    @property
    def redo_steps(self) -> int:
        raise NotImplementedError
