#!/usr/bin/env python3
"""Draw detected components and issue markers onto the source image.

Input: components.json from normalize_detections.py and optionally findings.json
(from analyze_layout.py, Sub-task 6) whose issues list numbered callouts.
Output: an annotated PNG. Local file processing only.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from common import (
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_USAGE,
    CliError,
    load_json,
    prepare_output_path,
    setup_logging,
    validate_image_path,
    validate_input_json,
)

log = logging.getLogger("carbon_placement.annotate")

PALETTE = ["#0f62fe", "#198038", "#8a3ffc", "#b28600", "#005d5d", "#9f1853", "#1192e8", "#6929c4"]
SEVERITY_COLOR = {"blocker": "#da1e28", "major": "#ff832b", "minor": "#f1c21b"}
LOW_CONFIDENCE_COLOR = "#8d8d8d"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Annotate an image with detected components and issues.")
    p.add_argument("--image", required=True)
    p.add_argument("--components", required=True, help="components.json")
    p.add_argument("--findings", default=None, help="Optional findings.json with numbered issues.")
    p.add_argument("--output", required=True, help="Annotated PNG path.")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    try:
        from PIL import Image, ImageDraw, ImageFont

        image_path = validate_image_path(args.image)
        comp_path = validate_input_json(args.components)
        find_path = validate_input_json(args.findings) if args.findings else None
        out_path = prepare_output_path(args.output, image_path)
        if out_path.suffix.lower() != ".png":
            raise CliError("Output must be a .png file.", EXIT_USAGE)

        comps = load_json(comp_path)
        if "components" not in comps or "scale_px_per_design_px" not in comps:
            raise CliError("Input is not a components file from normalize_detections.py.", EXIT_USAGE)
        scale = float(comps["scale_px_per_design_px"])
        findings: dict[str, Any] = load_json(find_path) if find_path else {}

        with Image.open(image_path) as src:
            canvas = src.convert("RGB")
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()
        stroke = max(2, round(canvas.width / 800))

        type_color: dict[str, str] = {}
        by_id: dict[str, list[float]] = {}
        for comp in comps["components"]:
            ctype = comp["carbon_type"] or "Unknown"
            color = LOW_CONFIDENCE_COLOR if comp.get("low_confidence") else type_color.setdefault(
                ctype, PALETTE[len(type_color) % len(PALETTE)]
            )
            x0, y0, x1, y1 = (v * scale for v in comp["box_design_px"])
            by_id[comp["id"]] = [x0, y0, x1, y1]
            draw.rectangle([x0, y0, x1, y1], outline=color, width=stroke)
            label = f"{comp['id']} {ctype} {comp['confidence']:.2f}"
            tw = draw.textlength(label, font=font)
            draw.rectangle([x0, max(0, y0 - 12), x0 + tw + 4, max(12, y0)], fill=color)
            draw.text((x0 + 2, max(0, y0 - 12)), label, fill="white", font=font)

        for number, issue in enumerate(findings.get("issues", []), 1):
            color = SEVERITY_COLOR.get(issue.get("severity", "minor"), SEVERITY_COLOR["minor"])
            for cid in issue.get("affected_component_ids", []):
                box = by_id.get(cid)
                if not box:
                    continue
                cx, cy, r = box[0], box[1], max(9, stroke * 4)
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
                draw.text((cx - r / 2, cy - 5), str(number), fill="white", font=font)

        canvas.save(out_path, format="PNG")
        log.info("Annotated image written", extra={"fields": {"components": len(comps["components"])}})
        return EXIT_OK
    except CliError as err:
        print(f"Error: {err}", file=sys.stderr)
        return err.exit_code
    except Exception:  # noqa: BLE001
        log.error("Unexpected failure", extra={"fields": {"stage": "annotate"}})
        print("Error: annotation failed unexpectedly.", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())
