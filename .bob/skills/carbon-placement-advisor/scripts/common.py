"""Shared helpers for the carbon-placement-advisor scripts.

Local-only utilities: JSON I/O, structured (JSON) logging to stderr, box math and
input validation. Nothing in this module opens a network connection.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = "1.0"
VOCAB_PATH = Path(__file__).with_name("prompt_vocab.json")
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_WEIGHTS = 4
EXIT_RUNTIME = 5

Box = Sequence[float]  # [x0, y0, x1, y1]


class CliError(Exception):
    """Expected, user-facing failure. The message is safe to show to end users."""

    def __init__(self, message: str, exit_code: int = EXIT_RUNTIME) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {"level": record.levelname, "message": record.getMessage()}
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            # Detailed errors go to the local log only, never to the user-facing message.
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Structured JSON logs on stderr. Never log tokens, secrets or full tracebacks."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger("PIL").setLevel(logging.INFO)  # silence PNG decoder chatter
    return logging.getLogger("carbon_placement")


def ensure_pkg_resources() -> None:
    """Provide a minimal pkg_resources if setuptools >= 82 removed it.

    sam3 only calls pkg_resources.resource_filename(package, resource). This shim
    avoids pinning an old setuptools (which the security rules discourage).
    """
    try:
        import pkg_resources  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    import importlib.resources
    import os
    import types

    shim = types.ModuleType("pkg_resources")

    def resource_filename(package: str, resource: str) -> str:
        return os.path.join(str(importlib.resources.files(package)), resource)

    shim.resource_filename = resource_filename  # type: ignore[attr-defined]
    sys.modules["pkg_resources"] = shim


def validate_image_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise CliError("Image file not found.", EXIT_USAGE)
    if p.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        raise CliError(
            f"Unsupported image type. Use one of: {', '.join(sorted(ALLOWED_IMAGE_SUFFIXES))}.",
            EXIT_USAGE,
        )
    return p


def validate_input_json(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file() or p.suffix.lower() != ".json":
        raise CliError("Input must be an existing .json file.", EXIT_USAGE)
    return p


def prepare_output_path(path: str, *protect: Path) -> Path:
    """Resolve an output path, create parent dirs, refuse to overwrite protected inputs."""
    out = Path(path).expanduser().resolve()
    if any(out == p for p in protect):
        raise CliError("Output path must differ from the input path.", EXIT_USAGE)
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        raise CliError("Could not read a valid JSON document from the input file.", EXIT_USAGE)
    if not isinstance(data, dict):
        raise CliError("Expected a JSON object at the top level.", EXIT_USAGE)
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def load_vocab(path: Path | None = None) -> dict[str, Any]:
    vocab = load_json(path or VOCAB_PATH)
    if "prompts" not in vocab or "geometry" not in vocab:
        raise CliError("Prompt vocabulary file is missing required sections.", EXIT_RUNTIME)
    return vocab


# --- box math -------------------------------------------------------------------------


def box_area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def intersection(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def iou(a: Box, b: Box) -> float:
    inter = intersection(a, b)
    union = box_area(a) + box_area(b) - inter
    return inter / union if union > 0 else 0.0
