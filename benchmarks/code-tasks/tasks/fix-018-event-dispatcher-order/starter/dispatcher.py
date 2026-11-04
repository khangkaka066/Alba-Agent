"""Synchronous publish/subscribe dispatcher."""

from registry import Registry


class Dispatcher:
    """Delivers payloads to the handlers subscribed to a topic.

    Handlers are called in the order given by ``Registry.matching``. A ``once``
    subscription is removed before its handler is called, so it never runs twice, even
    if the handler publishes the same topic again. Subscriptions added while a publish
    is in progress only take part in later publishes.
    """

    def __init__(self):
        self._registry = Registry()

    def subscribe(self, topic, handler, priority=0, once=False):
        return self._registry.add(topic, handler, priority, once)

    def unsubscribe(self, subscription):
        return self._registry.remove(subscription)

    def publish(self, topic, payload=None):
        """Call every matching handler with ``payload``; return their results in call order."""
        results = []
        for sub in self._registry.matching(topic):
            if sub.once:
                self._registry.remove(sub)
            results.append(sub.handler(payload))
        return results
