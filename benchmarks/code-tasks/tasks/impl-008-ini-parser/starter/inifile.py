def parse_ini(text: str) -> dict[str, dict[str, str]]:
    raise NotImplementedError


def get_bool(
    config: dict[str, dict[str, str]],
    section: str,
    key: str,
    default: bool | None = None,
) -> bool | None:
    raise NotImplementedError
