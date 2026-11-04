We keep the last N sensor readings in memory and need a small fixed-capacity buffer for that. Implement the `RingBuffer` class in `ringbuf.py`.

`RingBuffer(capacity)` holds at most `capacity` items. `capacity` must be an int >= 1, otherwise `ValueError` is raised.

- `push(item) -> bool`: appends `item` as the newest item. If the buffer was already full, the oldest item is discarded to make room and `True` is returned; otherwise `False` is returned.
- `pop_oldest()`: removes and returns the oldest item. Raises `IndexError` when empty.
- `peek_oldest()` / `peek_newest()`: return the oldest / newest item without removing it. Raise `IndexError` when empty.
- `len(buf)` is the number of items currently held; `buf.is_full()` is true when that equals the capacity; `bool(buf)` is false when empty.
- `buf[i]`: index 0 is the oldest item, `buf[-1]` the newest. Negative indexes count from the newest end. An index outside `-len(buf) <= i < len(buf)` raises `IndexError`.
- Iterating over the buffer yields the items from oldest to newest. `to_list()` returns them as a new list in the same order.
- `latest(n)`: the (up to) `n` newest items as a list, still ordered oldest to newest. If `n` exceeds the length, all items are returned; `n == 0` gives `[]`; negative `n` raises `ValueError`.
- `dropped`: read-only property, the total number of items discarded because of overwriting since creation (items removed with `pop_oldest()` or `clear()` do not count).
- `clear()`: removes all items (the `dropped` counter is kept).

Items may be any object, including `None`. Popping the oldest item makes room, so a later push on a buffer that was full before the pop does not discard anything.
