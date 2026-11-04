#!/usr/bin/env python3
"""Run SAM 3 (via sam3-mac) on one UI image with a list of text prompts.

Writes raw detections (prompt, box, score, mask area) to a JSON file. The image is
encoded once and reused for every prompt.

Local only: this script starts no network service. The one network access is the
HTTPS model-weights download by huggingface_hub on first run (gated repo facebook/sam3).
Authentication is read by huggingface_hub from `hf auth login` storage or the
HF_TOKEN environment variable. This script never reads, prints or stores a token.

Exit codes: 0 ok, 2 bad usage, 3 HuggingFace auth/access, 4 weights unavailable,
5 runtime failure.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

from common import (
    EXIT_AUTH,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_USAGE,
    EXIT_WEIGHTS,
    SCHEMA_VERSION,
    CliError,
    ensure_pkg_resources,
    load_vocab,
    prepare_output_path,
    setup_logging,
    validate_image_path,
    write_json,
)

log = logging.getLogger("carbon_placement.detect")

DEFAULT_THRESHOLD = 0.25  # all calibration and prompt testing was done at 0.25; 0.5 misses chevrons and steppers
DEFAULT_MAX_SIDE = 2048
DEFAULT_MAX_PER_PROMPT = 100
TOO_MANY_DETECTIONS = 400
MAX_PROMPTS = 64
MAX_PROMPT_LEN = 80


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect UI regions with SAM 3 text prompts.")
    p.add_argument("--image", required=True, help="Path to a PNG/JPG/WEBP image.")
    p.add_argument("--output", required=True, help="Path of the detections JSON to write.")
    p.add_argument(
        "--prompts",
        nargs="+",
        help="Noun-phrase prompts. Default: all prompts in prompt_vocab.json.",
    )
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Confidence 0-1.")
    p.add_argument(
        "--max-side",
        type=int,
        default=DEFAULT_MAX_SIDE,
        help="Downscale so the longest side is at most this many px (0 disables).",
    )
    p.add_argument("--max-per-prompt", type=int, default=DEFAULT_MAX_PER_PROMPT)
    p.add_argument("--device", choices=["auto", "mps", "cpu"], default="auto")
    p.add_argument(
        "--export-scale",
        type=float,
        default=None,
        help="Figma export scale (1 for @1x, 2 for @2x). Recorded for later px to design px.",
    )
    p.add_argument(
        "--frame-width",
        type=float,
        default=None,
        help="Frame width in design px (from Figma). Recorded for grid mapping.",
    )
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def validate_args(args: argparse.Namespace) -> list[dict[str, str]]:
    """Return the list of {prompt} to run. Raises CliError on bad input."""
    if not 0.0 < args.threshold < 1.0:
        raise CliError("--threshold must be between 0 and 1 (exclusive).", EXIT_USAGE)
    if args.max_side < 0 or args.max_per_prompt < 1:
        raise CliError("--max-side must be >= 0 and --max-per-prompt >= 1.", EXIT_USAGE)
    for name in ("export_scale", "frame_width"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            raise CliError(f"--{name.replace('_', '-')} must be greater than 0.", EXIT_USAGE)

    if args.prompts:
        if len(args.prompts) > MAX_PROMPTS:
            raise CliError(f"At most {MAX_PROMPTS} prompts are allowed.", EXIT_USAGE)
        prompts: list[dict[str, str]] = []
        for raw in args.prompts:
            text = " ".join(raw.split())
            if not text or len(text) > MAX_PROMPT_LEN:
                raise CliError("Each prompt must be 1-80 characters.", EXIT_USAGE)
            prompts.append({"prompt": text})
        return prompts
    # Default sweep: every prompt in prompt_vocab.json.
    return [{"prompt": e["prompt"]} for e in load_vocab()["prompts"]]


def pick_device(requested: str) -> str:
    ensure_pkg_resources()
    import sam3_mac

    return sam3_mac.install(None if requested == "auto" else requested)


def load_model(threshold: float):
    """Build SAM 3, translating hub failures into generic, actionable messages."""
    import sam3_mac

    try:
        return sam3_mac.build_image_model(confidence_threshold=threshold)
    except Exception as exc:  # noqa: BLE001 - classified below, details go to the log only
        log.error("Model build failed", extra={"fields": {"error_type": type(exc).__name__}})
        name = type(exc).__name__
        text = str(exc).lower()
        if name in {"GatedRepoError", "RepositoryNotFoundError"} or "401" in text or "403" in text:
            raise CliError(
                "Could not access the gated facebook/sam3 weights. Confirm your HuggingFace "
                "access request was approved and run `hf auth login` yourself.",
                EXIT_AUTH,
            )
        if name in {"LocalEntryNotFoundError", "OfflineModeIsEnabled"} or "connection" in text:
            raise CliError(
                "SAM 3 weights are not available locally and could not be downloaded. "
                "Check your network connection and disk space (about 5 GB needed).",
                EXIT_WEIGHTS,
            )
        raise CliError("SAM 3 model could not be built. See the log for the error type.", EXIT_RUNTIME)


def load_image(path: Path, max_side: int):
    from PIL import Image

    try:
        with Image.open(path) as im:
            im.load()
            rgb = im.convert("RGB")
    except Exception:  # noqa: BLE001
        raise CliError("The image could not be decoded.", EXIT_USAGE)
    orig_w, orig_h = rgb.size
    factor = 1.0
    if max_side and max(orig_w, orig_h) > max_side:
        factor = max_side / float(max(orig_w, orig_h))
        rgb = rgb.resize((max(1, round(orig_w * factor)), max(1, round(orig_h * factor))), Image.LANCZOS)
    return rgb, (orig_w, orig_h), factor


def run_prompts(
    processor, image, prompts: list[dict[str, str]], factor: float, max_per_prompt: int
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    state = processor.set_image(image)
    detections: list[dict[str, Any]] = []
    stats: dict[str, dict[str, Any]] = {}
    for entry in prompts:
        prompt = entry["prompt"]
        t0 = time.perf_counter()
        processor.reset_all_prompts(state)
        out = processor.set_text_prompt(prompt=prompt, state=state)
        boxes = out["boxes"].detach().float().cpu().numpy()
        scores = out["scores"].detach().float().cpu().numpy()
        masks = out["masks"]
        areas = masks.reshape(masks.shape[0], -1).sum(dim=1).cpu().numpy() if len(boxes) else []
        order = scores.argsort()[::-1][:max_per_prompt]
        for idx in order:
            x0, y0, x1, y1 = (float(v) / factor for v in boxes[idx])
            detections.append(
                {
                    "id": f"d{len(detections) + 1}",
                    "prompt": prompt,
                    "box": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                    "score": round(float(scores[idx]), 4),
                    "mask_area_px": int(round(float(areas[idx]) / (factor * factor))),
                }
            )
        stats[prompt] = {"count": int(len(order)), "seconds": round(time.perf_counter() - t0, 2)}
        log.info("Prompt done", extra={"fields": {"prompt": prompt, **stats[prompt]}})
    return detections, stats


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    try:
        image_path = validate_image_path(args.image)
        out_path = prepare_output_path(args.output, image_path)
        prompts = validate_args(args)

        image, (orig_w, orig_h), factor = load_image(image_path, args.max_side)
        t_start = time.perf_counter()
        device = pick_device(args.device)
        _model, processor = load_model(args.threshold)
        load_seconds = round(time.perf_counter() - t_start, 2)

        t_run = time.perf_counter()
        detections, stats = run_prompts(processor, image, prompts, factor, args.max_per_prompt)
        run_seconds = round(time.perf_counter() - t_run, 2)

        warnings: list[str] = []
        if not detections:
            warnings.append("no_detections: nothing passed the threshold. Lower --threshold or revise prompts.")
        if len(detections) > TOO_MANY_DETECTIONS:
            warnings.append(
                f"too_many_detections: {len(detections)} raw detections. Raise --threshold or reduce prompts."
            )
        if args.export_scale is None and args.frame_width is None:
            warnings.append(
                "scale_unknown: provide --frame-width (design px) or --export-scale so pixels can map to the grid."
            )
        if factor < 1.0:
            warnings.append(f"downscaled: image resized by {factor:.3f} for inference. Boxes are in original px.")

        write_json(
            out_path,
            {
                "schema_version": SCHEMA_VERSION,
                "image": {
                    "file_name": image_path.name,
                    "width_px": orig_w,
                    "height_px": orig_h,
                    "inference_downscale_factor": round(factor, 6),
                },
                "export_scale": args.export_scale,
                "frame_width_design_px": args.frame_width,
                "device": device,
                "threshold": args.threshold,
                "timing_seconds": {"model_load": load_seconds, "inference": run_seconds},
                "prompt_stats": stats,
                "detections": detections,
                "warnings": warnings,
            },
        )
        log.info(
            "Detections written",
            extra={"fields": {"count": len(detections), "warnings": len(warnings)}},
        )
        return EXIT_OK
    except CliError as err:
        print(f"Error: {err}", file=sys.stderr)
        return err.exit_code
    except Exception:  # noqa: BLE001 - never leak stack traces to the user
        log.error("Unexpected failure", exc_info=True)
        print("Error: detection failed unexpectedly. See the log output.", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())
