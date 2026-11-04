#!/usr/bin/env python3
"""Normalize raw SAM 3 detections into a clean Carbon component list.

SAM 3 returns shapes for a phrase, not Carbon types, so a prompt name is only a hint.

1. Convert boxes to design px using --export-scale (or frame width / image width).
2. A hit becomes a typed component only if its size and shape fit one of the prompt's
   candidate types (prompt_vocab.json "geometry"). Hits that fit none are dropped to
   unlabeled_leftovers with a reason. Nothing is guessed.
3. Helper hits (lines, chevrons, plus, minus, tab strip: types starting with "_") are
   evidence, never components. They are used to derive types:
     chevron inside a field            -> Dropdown
     plus and minus inside a field     -> NumberInput
     blue line at a tab strip's edge   -> Tab (selected); the strip -> Tab (unselected)
     a wide underline with no box      -> a field: TextInput, Dropdown, NumberInput or
                                          TextArea (see classify_underline_field)
4. Merge duplicates (IoU based), link child to parent by containment.

Pure local file processing. Input: detections JSON from detect_components.py.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from common import (
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_USAGE,
    SCHEMA_VERSION,
    CliError,
    box_area,
    intersection,
    iou,
    load_json,
    load_vocab,
    prepare_output_path,
    setup_logging,
    validate_image_path,
    validate_input_json,
    write_json,
)

log = logging.getLogger("carbon_placement.normalize")

DEDUPE_IOU = 0.6
CONTAIN_RATIO = 0.9
LOW_CONFIDENCE = 0.5
MIN_BOX_PX = 4.0  # drop boxes whose longest side is below this (thin lines are kept)

INPUT_TYPES = ("TextInput", "Dropdown", "NumberInput", "TextArea")
FIELD_HEIGHT = 40.0       # Carbon default field height; used to place the top of line-derived fields
LINE_MIN_W = 80.0         # shorter lines are labels or cell text; a 96 px Label field underline must still pass
LINE_MAX_H = 6.0
TOP_BORDER_TOL = 6.0       # px tolerance when matching a line to another field's top edge
TEXTAREA_GAP = 140.0      # HEURISTIC, tuned on 3 pages: space above an underline with no chevron/stepper
EDGE_TOL = 8.0
TAB_LABEL_GAP = 30.0      # px gap that separates two tab labels
INDICATOR_FRACTION = 0.30  # chevron / stepper must sit in the right 30 percent of a field
TAB_STRIP_MIN_W = 300.0   # a strip holds several tabs; narrower grey hits are pills or tags
TAB_STRIP_MIN_H = 32.0
CARD_EDGE_TOL = 6.0       # a line on a Tile's top or bottom edge is a card border, not a field
TABLE_EDGE_TOL = 6.0      # a line inside a DataTable box is a row divider, not a field
LINE_TAB_MIN_SEGMENTS = 3  # a row of this many touching underline segments is a line-tab row
LINE_TAB_MIN_W = 80.0
LINE_TAB_MAX_W = 260.0
LINE_TAB_Y_TOL = 4.0
LINE_TAB_JOIN_TOL = 6.0   # max x gap between neighbouring tab underlines
LINE_TAB_HEIGHT = 48.0    # Carbon tab height; used because only the underline is detected
SOLID_MAX_LUMA = 170.0    # a solid-fill button border is darker than this (white and light grey are not)
SOLID_MAX_STD = 14.0      # and uniform: the colour spread along the border band stays below this
SOLID_INSET_PX = 3        # sample the band this many image px inside the box edge


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Normalize SAM 3 detections into Carbon components.")
    p.add_argument("--input", required=True, help="detections.json from detect_components.py")
    p.add_argument("--output", required=True, help="components.json to write")
    p.add_argument("--image", default=None, help="Optional source image; lets tab labels be counted.")
    p.add_argument("--export-scale", type=float, default=None, help="Overrides the value in the input.")
    p.add_argument("--frame-width", type=float, default=None, help="Design width in px (overrides input).")
    p.add_argument("--dedupe-iou", type=float, default=DEDUPE_IOU)
    p.add_argument("--min-confidence", type=float, default=0.0, help="Drop components below this.")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def resolve_scale(doc: dict[str, Any], args: argparse.Namespace) -> tuple[float, list[str]]:
    """Return px-per-design-px and warnings. Raises CliError if scale cannot be known."""
    notes: list[str] = []
    scale = args.export_scale or doc.get("export_scale")
    frame_w = args.frame_width or doc.get("frame_width_design_px")
    img_w = float(doc["image"]["width_px"])
    if scale is None and frame_w:
        scale = img_w / float(frame_w)
        notes.append(f"scale_derived: export scale inferred as {scale:.3f} from frame width.")
    if scale is None:
        raise CliError(
            "Image scale is unknown. Provide --frame-width (design px) or --export-scale.", EXIT_USAGE
        )
    if scale <= 0:
        raise CliError("Scale must be greater than 0.", EXIT_USAGE)
    if frame_w and abs(img_w / scale - float(frame_w)) > 0.02 * float(frame_w):
        notes.append("scale_mismatch: image width / scale differs from frame width by more than 2 percent.")
    return float(scale), notes


# --- classification --------------------------------------------------------------------


def geometry_fit(ctype: str, w: float, h: float, rules: dict[str, Any]) -> float:
    """Fraction of geometry rules satisfied, 0..1. A type with no rules passes (1.0)."""
    spec = rules.get(ctype)
    if not spec or w <= 0 or h <= 0:
        return 1.0
    aspect = w / h
    checks = [
        ("min_w", w >= spec.get("min_w", 0)),
        ("max_w", w <= spec.get("max_w", float("inf"))),
        ("min_h", h >= spec.get("min_h", 0)),
        ("max_h", h <= spec.get("max_h", float("inf"))),
        ("min_aspect", aspect >= spec.get("min_aspect", 0)),
        ("max_aspect", aspect <= spec.get("max_aspect", float("inf"))),
    ]
    relevant = [ok for key, ok in checks if key in spec]
    return sum(relevant) / len(relevant) if relevant else 1.0


def classify(det: dict[str, Any], w: float, h: float, vocab: dict[str, Any]) -> tuple[str | None, float]:
    """Return (type, confidence). Helper types start with "_". None when no type fits."""
    entry = next((e for e in vocab["prompts"] if e["prompt"] == det["prompt"]), None)
    if not entry:
        return None, 0.0
    hint = entry["types"]
    if hint[0].startswith("_"):
        return hint[0], round(float(det["score"]), 3)
    for ctype in hint:  # first fully fitting type wins; hint order expresses preference
        if geometry_fit(ctype, w, h, vocab["geometry"]) >= 1.0:
            return ctype, round(float(det["score"]), 3)
    return None, 0.0


def solid_fill_button(image_path: Path | None, box_px: list[float]) -> bool:
    """True if the box border is one solid dark or saturated colour, like a primary or danger button.

    SAM 3 often returns a button for the prompt "rectangle" instead of "button". That prompt maps to
    Tile, which is too tall, so the hit is dropped. Dark or solid fill is evidence of a filled button
    that white fields, white tabs and light grey table headers do not have. Ghost and secondary
    buttons have no solid fill and are not recovered by this check.
    """
    if image_path is None:
        return False
    import numpy as np
    from PIL import Image

    with Image.open(image_path) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
    x0, y0, x1, y1 = (int(round(v)) for v in box_px)
    i = SOLID_INSET_PX
    if x1 - x0 < 4 * i or y1 - y0 < 4 * i:
        return False
    band = np.concatenate([
        rgb[y0 + i, x0 + i:x1 - i].reshape(-1, 3),
        rgb[y1 - i, x0 + i:x1 - i].reshape(-1, 3),
        rgb[y0 + i:y1 - i, x0 + i].reshape(-1, 3),
        rgb[y0 + i:y1 - i, x1 - i].reshape(-1, 3),
    ])
    luma = band @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    return bool(np.median(luma) < SOLID_MAX_LUMA and float(luma.std()) < SOLID_MAX_STD)


def merge_duplicates(items: list[dict[str, Any]], thresh: float) -> list[dict[str, Any]]:
    """Greedy NMS by confidence. Boxes above the IoU threshold are one region: the most
    confident type wins and competing types are kept as alt_types (type is ambiguous)."""
    kept: list[dict[str, Any]] = []
    for it in sorted(items, key=lambda d: d["confidence"], reverse=True):
        dup = next((k for k in kept if iou(k["box_design_px"], it["box_design_px"]) >= thresh), None)
        if dup is None:
            it["source_detections"] = [it["source_detection"]]
            it["alt_types"] = []
            kept.append(it)
        else:
            dup["source_detections"].append(it["source_detection"])
            if it["carbon_type"] != dup["carbon_type"] and it["carbon_type"] not in dup["alt_types"]:
                dup["alt_types"].append(it["carbon_type"])
    return kept


# --- helper-driven typing ----------------------------------------------------------------


def _center(b: list[float]) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _in_indicator_zone(helper_box: list[float], field: list[float]) -> bool:
    cx, cy = _center(helper_box)
    right_start = field[2] - INDICATOR_FRACTION * (field[2] - field[0])
    return right_start <= cx <= field[2] and field[1] - 4 <= cy <= field[3] + 4


def indicator_type(field: list[float], helpers: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    """Dropdown if a chevron sits in the field's right zone; NumberInput if plus and minus do."""
    inside = {k: [h for h in helpers if h["carbon_type"] == k and _in_indicator_zone(h["box_design_px"], field)]
              for k in ("_Chevron", "_Plus", "_Minus")}
    if inside["_Chevron"]:
        return "Dropdown", ["chevron inside field"]
    if inside["_Plus"] and inside["_Minus"]:
        return "NumberInput", ["plus and minus inside field"]
    return None, []


def _x_overlap(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))


def classify_underline_field(
    field: list[float], others: list[list[float]], helpers: list[dict[str, Any]]
) -> tuple[str, list[str], float]:
    """Type for a field known only by its underline. Returns (type, evidence, confidence).

    Order: chevron -> Dropdown, plus+minus -> NumberInput (measured evidence). Otherwise,
    if there is a large vertical gap above the field (> TEXTAREA_GAP to the nearest object
    that overlaps it horizontally) -> TextArea (HEURISTIC). Otherwise TextInput, which means
    only "no chevron or stepper found": SAM 3 cannot tell a text input from other plain fields.
    """
    kind, evidence = indicator_type(field, helpers)
    if kind:
        return kind, evidence, 0.7
    width = field[2] - field[0]
    above = [o[3] for o in others
             if o[3] < field[3] - 10 and _x_overlap(field, o) >= 0.3 * min(width, o[2] - o[0])]
    if above and field[3] - max(above) > TEXTAREA_GAP:
        return "TextArea", [f"{round(field[3] - max(above))}px empty space above, no chevron or stepper (heuristic)"], 0.5
    return "TextInput", ["no chevron or stepper found"], 0.55


def split_tab_labels(image_path: Path, strip_px: list[float]) -> list[tuple[float, float]]:
    """Return label x-ranges (image px) inside a tab strip by clustering non-background columns."""
    import numpy as np
    from PIL import Image

    with Image.open(image_path) as im:
        gray = np.asarray(im.convert("L"), dtype=np.int16)
    x0, y0, x1, y1 = (int(round(v)) for v in strip_px)
    band = gray[y0 + 10:max(y0 + 11, y1 - 10), x0:x1]
    if band.size == 0:
        return []
    background = int(np.median(band))
    cols = (np.abs(band - background) > 40).any(axis=0)
    runs: list[list[int]] = []
    for i, on in enumerate(cols):
        if not on:
            continue
        if runs and i - runs[-1][1] <= TAB_LABEL_GAP:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return [(x0 + a, x0 + b) for a, b in runs]


def make_component(box: list[float], ctype: str, conf: float, **extra: Any) -> dict[str, Any]:
    comp = {
        "box_design_px": [round(v, 1) for v in box],
        "carbon_type": ctype,
        "confidence": round(conf, 3),
        "source_detection": None,
        "source_detections": [],
        "alt_types": [],
        "prompt": "derived",
    }
    comp.update(extra)
    return comp


def derive_from_helpers(
    components: list[dict[str, Any]],
    helpers: list[dict[str, Any]],
    image_path: Path | None,
    scale: float,
    notes: list[str],
) -> list[dict[str, Any]]:
    """Refine SAM-box inputs and create Tab / field components from helper hits."""
    # 1. SAM-detected inputs: chevron / stepper decides Dropdown / NumberInput.
    for comp in components:
        if comp["carbon_type"] in ("TextInput", "Dropdown"):
            kind, evidence = indicator_type(comp["box_design_px"], helpers)
            if kind and kind != comp["carbon_type"]:
                comp["alt_types"].append(comp["carbon_type"])
                comp["carbon_type"] = kind
            if kind:
                comp["type_evidence"] = evidence

    lines = [h for h in helpers if h["carbon_type"] == "_Line"
             and (h["box_design_px"][2] - h["box_design_px"][0]) >= LINE_MIN_W
             and (h["box_design_px"][3] - h["box_design_px"][1]) <= LINE_MAX_H]
    used_lines: set[str] = set()
    derived: list[dict[str, Any]] = []

    # 2. Tabs: a tab strip is the unselected tabs; a line at its left edge is the selected tab.
    strips = [h for h in helpers if h["carbon_type"] == "_TabStrip"
              and (h["box_design_px"][2] - h["box_design_px"][0]) >= TAB_STRIP_MIN_W
              and (h["box_design_px"][3] - h["box_design_px"][1]) >= TAB_STRIP_MIN_H]
    for strip in strips:
        sb = strip["box_design_px"]
        selected = next((ln for ln in lines
                         if abs(ln["box_design_px"][2] - sb[0]) <= EDGE_TOL
                         and abs(ln["box_design_px"][1] - sb[1]) <= EDGE_TOL), None)
        top = min(sb[1], selected["box_design_px"][1]) if selected else sb[1]
        if selected:
            used_lines.add(selected["source_detection"])
            lb = selected["box_design_px"]
            derived.append(make_component(
                [lb[0], top, lb[2], sb[3]], "Tab", min(selected["confidence"], strip["confidence"]),
                state="selected", type_evidence=["blue indicator line at the left edge of the tab strip"]))
        labels = split_tab_labels(image_path, [v * scale for v in sb]) if image_path else []
        if len(labels) >= 2:
            labels = [(a / scale, b / scale) for a, b in labels]
            edges = [sb[0]] + [(labels[i][1] + labels[i + 1][0]) / 2 for i in range(len(labels) - 1)] + [sb[2]]
            for i in range(len(labels)):
                derived.append(make_component(
                    [edges[i], sb[1], edges[i + 1], sb[3]], "Tab", strip["confidence"], state="unselected",
                    edges_estimated=True,
                    type_evidence=[f"{len(labels)} labels counted in the grey strip; tab edges estimated midway between labels"]))
        else:
            derived.append(make_component(
                list(sb), "Tab", strip["confidence"], state="unselected", group=True,
                type_evidence=["grey tab strip; individual tabs not separated (pass --image to count labels)"]))
            notes.append("tabs_not_split: pass --image to normalize_detections.py to split unselected tabs.")

    # 2b. Line tabs: several underline segments that touch end to end at one y are a tab row.
    # Any wider line at the same y inside the row is the row's rule, so it is used up too.
    free = [ln for ln in lines if ln["source_detection"] not in used_lines]
    segs = [ln for ln in free
            if LINE_TAB_MIN_W <= ln["box_design_px"][2] - ln["box_design_px"][0] <= LINE_TAB_MAX_W]
    chains: list[list[dict[str, Any]]] = []
    for ln in sorted(segs, key=lambda h: (round(h["box_design_px"][3] / LINE_TAB_Y_TOL), h["box_design_px"][0])):
        lb = ln["box_design_px"]
        for chain in chains:
            last = chain[-1]["box_design_px"]
            if abs(last[3] - lb[3]) <= LINE_TAB_Y_TOL and 0 <= lb[0] - last[2] <= LINE_TAB_JOIN_TOL:
                chain.append(ln)
                break
        else:
            chains.append([ln])
    for chain in chains:
        if len(chain) < LINE_TAB_MIN_SEGMENTS:
            continue
        x0, x1 = chain[0]["box_design_px"][0], chain[-1]["box_design_px"][2]
        y1 = max(s["box_design_px"][3] for s in chain)
        for s in chain:
            used_lines.add(s["source_detection"])
            sb = s["box_design_px"]
            derived.append(make_component(
                [sb[0], y1 - LINE_TAB_HEIGHT, sb[2], y1], "Tab", s["confidence"], state="unknown",
                geometry_source="underline", top_edge_estimated=True,
                type_evidence=[f"{len(chain)} underline segments touch end to end: a line-tab row"]))
        for ln in free:
            lb = ln["box_design_px"]
            if (ln["source_detection"] not in used_lines and abs(lb[3] - y1) <= LINE_TAB_Y_TOL
                    and lb[0] >= x0 - EDGE_TOL and lb[2] <= x1 + EDGE_TOL):
                used_lines.add(ln["source_detection"])

    # 3. Fields known only by an underline (no SAM box around them).
    boxes = [c["box_design_px"] for c in components + derived]
    candidates: list[dict[str, Any]] = []
    for ln in sorted(lines, key=lambda h: (h["box_design_px"][3], h["box_design_px"][0])):
        if ln["source_detection"] in used_lines:
            continue
        lb = ln["box_design_px"]
        bordering = any(
            c["carbon_type"] in INPUT_TYPES
            and c["box_design_px"][1] - 6 <= lb[1] and lb[3] <= c["box_design_px"][3] + 6
            and _x_overlap(lb, c["box_design_px"]) >= 0.5 * (lb[2] - lb[0])
            for c in components)
        if bordering:  # the border of a field SAM already boxed
            continue
        card_border = any(
            c["carbon_type"] == "Tile"
            and _x_overlap(lb, c["box_design_px"]) >= 0.9 * (lb[2] - lb[0])
            and (abs(lb[1] - c["box_design_px"][1]) <= CARD_EDGE_TOL
                 or abs(lb[3] - c["box_design_px"][3]) <= CARD_EDGE_TOL)
            for c in components)
        if card_border:
            continue
        table_row = any(
            c["carbon_type"] == "DataTable"
            and c["box_design_px"][1] - TABLE_EDGE_TOL <= lb[1] and lb[3] <= c["box_design_px"][3] + TABLE_EDGE_TOL
            and _x_overlap(lb, c["box_design_px"]) >= 0.5 * (lb[2] - lb[0])
            for c in components)
        if table_row:  # a row divider inside a detected table
            continue
        candidates.append(ln)
    # A fully outlined field (error state, NumberInput) has a top border line too; that line sits
    # one field-height above another candidate line with the same width, so it is not a new field.
    def _is_top_border(ln: dict[str, Any]) -> bool:
        lb = ln["box_design_px"]
        return any(
            other is not ln
            and abs((other["box_design_px"][3] - FIELD_HEIGHT) - lb[3]) <= TOP_BORDER_TOL
            and _x_overlap(lb, other["box_design_px"]) >= 0.9 * (lb[2] - lb[0])
            and _x_overlap(lb, other["box_design_px"]) >= 0.9 * (other["box_design_px"][2] - other["box_design_px"][0])
            for other in candidates)
    candidates = [ln for ln in candidates if not _is_top_border(ln)]
    field_boxes = [[ln["box_design_px"][0], ln["box_design_px"][3] - FIELD_HEIGHT,
                    ln["box_design_px"][2], ln["box_design_px"][3]] for ln in candidates]
    for ln, fb in zip(candidates, field_boxes):
        others = boxes + [b for b in field_boxes if b is not fb]
        ctype, evidence, conf = classify_underline_field(fb, others, helpers)
        derived.append(make_component(
            fb, ctype, min(conf, ln["confidence"] + 0.0) if conf > 0.6 else conf,
            geometry_source="underline", top_edge_estimated=True, type_evidence=evidence))
    return derived


def link_containment(items: list[dict[str, Any]]) -> None:
    """Set parent_id to the smallest item that contains >= CONTAIN_RATIO of the child."""
    for child in items:
        c_area = box_area(child["box_design_px"])
        best, best_area = None, float("inf")
        for parent in items:
            if parent is child:
                continue
            p_area = box_area(parent["box_design_px"])
            if p_area <= c_area:
                continue
            if intersection(child["box_design_px"], parent["box_design_px"]) / max(c_area, 1e-9) >= CONTAIN_RATIO:
                if p_area < best_area:
                    best, best_area = parent, p_area
        child["parent_id"] = best["id"] if best else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    try:
        in_path = validate_input_json(args.input)
        out_path = prepare_output_path(args.output, in_path)
        image_path = validate_image_path(args.image) if args.image else None
        if not 0.0 < args.dedupe_iou <= 1.0 or not 0.0 <= args.min_confidence <= 1.0:
            raise CliError("--dedupe-iou must be in (0,1] and --min-confidence in [0,1].", EXIT_USAGE)

        doc = load_json(in_path)
        if "detections" not in doc or "image" not in doc:
            raise CliError("Input is not a detections file from detect_components.py.", EXIT_USAGE)
        vocab = load_vocab()
        scale, warnings = resolve_scale(doc, args)

        typed: list[dict[str, Any]] = []
        helpers: list[dict[str, Any]] = []
        leftovers: list[dict[str, Any]] = []
        for det in doc["detections"]:
            box = [float(v) / scale for v in det["box"]]
            w, h = box[2] - box[0], box[3] - box[1]
            if max(w, h) < MIN_BOX_PX or min(w, h) < 1.0:
                continue
            ctype, conf = classify(det, w, h, vocab)
            button_evidence = None
            if (ctype is None and det["prompt"] == "rectangle"
                    and geometry_fit("Button", w, h, vocab["geometry"]) >= 1.0
                    and solid_fill_button(image_path, [v * scale for v in box])):
                ctype, conf = "Button", round(float(det["score"]), 3)
                button_evidence = ["rectangle with a solid dark or saturated fill, button-sized"]
            record = {
                "box_design_px": [round(v, 1) for v in box],
                "carbon_type": ctype,
                "confidence": conf,
                "source_detection": det["id"],
                "prompt": det["prompt"],
                "sam_score": det["score"],
            }
            if button_evidence:
                record["type_evidence"] = button_evidence
            if ctype and ctype.startswith("_"):
                helpers.append(record)
            elif ctype and conf >= args.min_confidence:
                typed.append(record)
            else:
                record["reason"] = "geometry_mismatch" if ctype is None else "below_min_confidence"
                leftovers.append(record)

        merged = merge_duplicates(typed, args.dedupe_iou)
        merged.extend(derive_from_helpers(merged, helpers, image_path, scale, warnings))
        for idx, comp in enumerate(sorted(merged, key=lambda c: (c["box_design_px"][1], c["box_design_px"][0])), 1):
            comp["id"] = f"c{idx}"
            comp["low_confidence"] = comp["confidence"] < LOW_CONFIDENCE
        link_containment(merged)
        merged.sort(key=lambda c: int(c["id"][1:]))

        if not merged:
            warnings.append("no_components: no detections could be classified. Check prompts and threshold.")
        write_json(
            out_path,
            {
                "schema_version": SCHEMA_VERSION,
                "image": doc["image"],
                "scale_px_per_design_px": round(scale, 4),
                "frame_width_design_px": round(doc["image"]["width_px"] / scale, 1),
                "frame_height_design_px": round(doc["image"]["height_px"] / scale, 1),
                "components": merged,
                "helper_hits": helpers,
                "unlabeled_leftovers": leftovers,
                "warnings": warnings + list(doc.get("warnings", [])),
            },
        )
        log.info(
            "Components written",
            extra={"fields": {"components": len(merged), "helpers": len(helpers), "leftovers": len(leftovers)}},
        )
        return EXIT_OK
    except CliError as err:
        print(f"Error: {err}", file=sys.stderr)
        return err.exit_code
    except Exception:  # noqa: BLE001
        log.error("Unexpected failure", exc_info=True)
        print("Error: normalization failed unexpectedly. See the log output.", file=sys.stderr)
        return EXIT_RUNTIME


if __name__ == "__main__":
    sys.exit(main())
