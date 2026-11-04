"""In-memory session store with a time-to-live. Times are plain numbers (seconds)."""


class SessionStore:
    """Sessions expire once ``now - last_seen >= ttl``."""

    def __init__(self, ttl):
        self.ttl = ttl
        self._last_seen = {}

    def _expired(self, last_seen, now):
        return now - last_seen >= self.ttl

    def create(self, session_id, now):
        """Start (or restart) a session at time ``now``."""
        self._last_seen[session_id] = now

    def touch(self, session_id, now):
        """Refresh a live session and return True.

        Returns False and changes nothing if the session is unknown or has
        already expired; an expired session stays expired until ``purge``
        removes it (touching it must not bring it back).
        """
        if session_id not in self._last_seen:
            return False
        self._last_seen[session_id] = now
        return True

    def is_active(self, session_id, now):
        """True if the session exists and has not expired."""
        seen = self._last_seen.get(session_id)
        return seen is not None and not self._expired(seen, now)

    def purge(self, now):
        """Delete every expired session and return the sorted list of removed ids."""
        removed = []
        for session_id, seen in self._last_seen.items():
            if self._expired(seen, now):
                del self._last_seen[session_id]
                removed.append(session_id)
        return sorted(removed)

    def active_count(self, now):
        """Number of sessions that have not expired."""
        return sum(1 for seen in self._last_seen.values() if not self._expired(seen, now))
