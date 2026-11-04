#!/usr/bin/env python3
"""Run the whole review pipeline on one image with a single command.

    detect_components -> normalize_detections -> analyze_layout -> annotate_image

Writes four files into --output-dir:
    detections.json   raw SAM 3 hits
    components.json   Carbon-typed components
    findings.json     numbered placement issues
    annotated.png     the image with boxes and numbered issue markers

Local only. It calls the other scripts' main() functions in this process (no shell,
no subprocess, no network service).

Exit codes: 0 ok, 2 bad usage, 3 HuggingFace access, 4 weights unavailable, 5 runtime failure.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import sys
from pathlib import Path

from common import (
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_USAGE,
    CliError,
    prepare_output_path,
    setup_logging,
    validate_image_path,
)

log = logging.getLogger("carbon_placement.run_review")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect, normalize, analyze and annotate one UI image.")
    p.add_argument("--image", required=True, help="PNG/JPG/WEBP screenshot or Figma export.")
    p.add_argument("--output-dir", required=True, help="Folder for the four result files.")
    p.add_argument("--frame-width", type=float, default=None, help="Frame width in design px (from Figma).")
    p.add_argument("--export-scale", type=float, default=None, help="Export scale: 1 for @1x, 2 for @2x.")
    p.add_argument("--threshold", type=float, default=None, help="SAM 3 confidence 0-1 (default 0.25, the value used for tuning).")
    p.add_argument("--device", choices=["auto", "mps", "cpu"], default="auto")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def _opt(flag: str, value) -> list[str]:
    return [flag, str(value)] if value is not None else []


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    try:
        if args.frame_width is None and args.export_scale is None:
            raise CliError(
                "Provide --frame-width (design px) or --export-scale. "
                "Without one the pixels cannot be mapped to the Carbon grid.",
                EXIT_USAGE,
            )
        image = validate_image_path(args.image)
        out_dir = prepare_output_path(str(Path(args.output_dir) / ".keep")).parent
        det, comp, find, png = (
            out_dir / n for n in ("detections.json", "components.json", "findings.json", "annotated.png")
        )

        # Imported here so --help and argument errors work without loading torch.
        import analyze_layout
        import annotate_image
        import detect_components
        import normalize_detections

        verbose = ["--verbose"] if args.verbose else []
        steps = [
            (
                "detect",
                lambda: detect_components.main(
                    ["--image", str(image), "--output", str(det), "--device", args.device]
                    + _opt("--frame-width", args.frame_width)
                    + _opt("--export-scale", args.export_scale)
                    + _opt("--threshold", args.threshold)
                    + verbose
                ),
            ),
            (
                "normalize",
                lambda: normalize_detections.main(
                    ["--input", str(det), "--output", str(comp), "--image", str(image)] + verbose
                ),
            ),
        ]
        for name, step in steps:
            code = step()
            if code != EXIT_OK:
                print(f"Error: the {name} step failed (exit {code}).", file=sys.stderr)
                return code
            log.info("Step done", extra={"fields": {"step": name}})

        with contextlib.redirect_stdout(sys.stderr):  # keep stdout for the JSON summary only
            report = analyze_layout.run_analysis_on_file(str(comp), str(find))
        if report is None:
            raise CliError("Layout analysis produced no report.", EXIT_RUNTIME)
        log.info("Step done", extra={"fields": {"step": "analyze", "issues": report["total_issues"]}})

        code = annotate_image.main(
            ["--image", str(image), "--components", str(comp), "--findings", str(find), "--output", str(png)]
            + verbose
        )
        if code != EXIT_OK:
            print(f"Error: the annotate step failed (exit {code}).", file=sys.stderr)
            return code

        components = json.loads(comp.read_text(encoding="utf-8"))
        summary = {
            "output_dir": str(out_dir),
            "components": len(components["components"]),
            "issues": report["total_issues"],
            "warnings": components.get("warnings", []),
            "files": [p.name for p in (det, comp, find, png)],
        }
        print(json.dumps(summary, indent=2))
        return EXIT_OK
    except CliError as err:
        print(f"Error: {err}", file=sys.stderr)
        return err.exit_code
    except Exception:  # noqa: BLE001 - never show a stack trace to the user
        log.error("Unexpected failure", exc_info=True)
        print("Error: the review failed unexpectedly. See the log output.", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())
