"""Subscription storage and topic matching for the event dispatcher."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Subscription:
    topic: str
    handler: Callable[[Any], Any]
    priority: int
    seq: int
    once: bool = False


def topic_matches(pattern, topic):
    """True when ``pattern`` selects ``topic``.

    ``"*"`` matches every topic. A pattern ending in ``".*"`` matches every topic that
    starts with the part before the star, at any depth: ``"orders.*"`` matches
    ``"orders.created"`` and ``"orders.item.added"`` but not ``"orders"`` or
    ``"ordersx.created"``. Any other pattern must equal the topic exactly.
    """
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return topic.startswith(pattern[:-1])
    return pattern == topic


class Registry:
    def __init__(self):
        self._subs = []
        self._next_seq = 0

    def add(self, topic, handler, priority=0, once=False):
        sub = Subscription(topic, handler, priority, self._next_seq, once)
        self._next_seq += 1
        self._subs.append(sub)
        return sub

    def remove(self, sub):
        """Remove a subscription. Returns True if it was registered."""
        if sub in self._subs:
            self._subs.remove(sub)
            return True
        return False

    def matching(self, topic):
        """Subscriptions that should receive ``topic``, in call order.

        One single order applies to exact and wildcard subscriptions alike: higher
        ``priority`` first, and among equal priorities the one subscribed earlier first.
        """
        exact = [s for s in self._subs if s.topic == topic]
        wild = [s for s in self._subs if s.topic != topic and topic_matches(s.topic, topic)]
        key = lambda s: (-s.priority, s.seq)
        return sorted(exact, key=key) + sorted(wild, key=key)
