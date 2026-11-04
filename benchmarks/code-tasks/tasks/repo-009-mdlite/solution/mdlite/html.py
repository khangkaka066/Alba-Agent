"""HTML escaping."""


def escape(text):
    """Replace ``&`` with ``&amp;``, ``<`` with ``&lt;``, ``>`` with ``&gt;`` and ``"`` with ``&quot;``. Each character of the
    input is replaced exactly once: text that already looks like an entity is escaped as ordinary text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
