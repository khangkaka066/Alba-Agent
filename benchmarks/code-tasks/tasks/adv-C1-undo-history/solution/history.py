from __future__ import annotations

import copy


class History:
    def __init__(self, initial, limit=None) -> None:
        if limit is not None and limit < 1:
            raise ValueError("limit must be >= 1")
        self._limit = limit
        self._states = [copy.deepcopy(initial)]
        self._idx = 0

    @property
    def current(self):
        return copy.deepcopy(self._states[self._idx])

    def commit(self, state) -> bool:
        if state == self._states[self._idx]:
            return False
        del self._states[self._idx + 1:]
        self._states.append(copy.deepcopy(state))
        self._idx += 1
        if self._limit is not None and self._idx > self._limit:
            drop = self._idx - self._limit
            del self._states[:drop]
            self._idx -= drop
        return True

    def undo(self):
        if self._idx == 0:
            raise IndexError("nothing to undo")
        self._idx -= 1
        return self.current

    def redo(self):
        if self._idx >= len(self._states) - 1:
            raise IndexError("nothing to redo")
        self._idx += 1
        return self.current

    @property
    def can_undo(self) -> bool:
        return self._idx > 0

    @property
    def can_redo(self) -> bool:
        return self._idx < len(self._states) - 1

    @property
    def undo_steps(self) -> int:
        return self._idx

    @property
    def redo_steps(self) -> int:
        return len(self._states) - 1 - self._idx
