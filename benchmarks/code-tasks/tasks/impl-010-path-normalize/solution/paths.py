def normalize_path(path: str) -> str:
    absolute = path.startswith("/")
    stack: list[str] = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if stack and stack[-1] != "..":
                stack.pop()
            elif not absolute:
                stack.append("..")
            continue
        stack.append(segment)
    joined = "/".join(stack)
    if absolute:
        return "/" + joined
    return joined or "."


def join_paths(base: str, *parts: str) -> str:
    result = base
    for part in parts:
        if not part:
            continue
        if part.startswith("/") or not result:
            result = part
        else:
            result = result + "/" + part
    return normalize_path(result)
