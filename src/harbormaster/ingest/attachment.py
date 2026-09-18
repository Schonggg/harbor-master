from pathlib import Path


def sniff_type(path: str | Path) -> str:
    return Path(path).suffix.lower().lstrip('.') or 'txt'
