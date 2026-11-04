class SqlError(Exception):
    """Raised for every problem with a statement: bad syntax, unknown table or column, type or constraint violation."""
