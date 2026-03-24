from __future__ import annotations

from pathlib import Path
import re


def parse_simple_yaml(path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    lines = path.read_text(encoding="utf-8").splitlines()

    section = ""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if re.match(r"^\S", line):
            section = ""
            if ":" not in line:
                raise ValueError(f"Invalid YAML line: {line!r}")
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                section = key
                if key in ("agents", "agent"):
                    result[key] = []
                continue
            result[key] = parse_scalar(value)
            continue

        if section in ("agents", "agent"):
            if not stripped.startswith("- "):
                raise ValueError(f"Invalid {section} list item, expected '- value'.")
            item = parse_scalar(stripped[2:])
            casted = result.setdefault(section, [])
            if isinstance(casted, list):
                casted.append(item)
            continue

    return result


def parse_scalar(value: str) -> object:
    text = value.strip()
    if text.startswith(("'", '"')) and text.endswith(("'", '"')) and len(text) >= 2:
        text = text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def normalize_identifier(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"\s+", "-", lowered)
    lowered = re.sub(r"[^a-z0-9\-]", "", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered
