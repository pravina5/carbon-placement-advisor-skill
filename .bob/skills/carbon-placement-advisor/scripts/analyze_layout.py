"""
Carbon Layout Analysis Engine (Calibrated with Designer Feedback)
Analyzes detected UI component bounding boxes against Carbon Design System rules:
1. 2x Grid column alignment & span calculation (16/8/4 columns).
2. Gap between sibling fields (relative to the grid) & floating action buttons.
3. Form input sizing (mismatched widths, undersized inputs).
4. Subheading / subtitle left-edge alignment with page header.
5. Vertical row baseline misalignment (e.g. shifted inputs).
"""

import math
import json
import os
import sys

# Carbon Spacing Scale Tokens ($spacing-01 to $spacing-13)
SPACING_TOKENS = {
    "$spacing-01": 2,
    "$spacing-02": 4,
    "$spacing-03": 8,
    "$spacing-04": 12,
    "$spacing-05": 16,
    "$spacing-06": 24,
    "$spacing-07": 32,
    "$spacing-08": 40,
    "$spacing-09": 48,
    "$spacing-10": 64,
    "$spacing-11": 80,
    "$spacing-12": 96,
    "$spacing-13": 160,
}

# Carbon Breakpoint Specs
BREAKPOINTS = {
    "sm": {"cols": 4, "gutter": 16, "margin": 16},
    "md": {"cols": 8, "gutter": 16, "margin": 16},
    "lg": {"cols": 16, "gutter": 32, "margin": 16},
    "xlg": {"cols": 16, "gutter": 32, "margin": 16},
    "max": {"cols": 16, "gutter": 32, "margin": 24},
}

def get_nearest_spacing_token(pixel_gap: int):
    """Finds the closest Carbon spacing token and tolerance delta."""
    best_token = None
    min_diff = float("inf")
    for token, val in SPACING_TOKENS.items():
        diff = abs(pixel_gap - val)
        if diff < min_diff:
            min_diff = diff
            best_token = token
    return best_token, SPACING_TOKENS[best_token], min_diff

def calculate_grid_span(width_px: int, frame_width: int = 1312, bp_name: str = "lg"):
    """Calculates column span and target snapping width for a given breakpoint."""
    bp = BREAKPOINTS.get(bp_name, BREAKPOINTS["lg"])
    cols = bp["cols"]
    gutter = bp["gutter"]
    margin = bp["margin"]

    content_w = frame_width - (2 * margin)
    total_gutters = (cols - 1) * gutter
    col_w = (content_w - total_gutters) / cols
    pitch = col_w + gutter

    span = math.ceil((width_px + gutter) / pitch)
    span = max(1, min(cols, span))
    standard_width = round((span * col_w) + ((span - 1) * gutter))
    return span, standard_width, round(col_w), gutter

def analyze_layout(detections: list, frame_width: int = 1312, frame_height: int = 738, bp_name: str = "lg"):
    """Runs calibrated layout analysis against detected components."""
    findings = []
    issue_counter = 1

    # Filter components by type
    dropdowns = [c for c in detections if c.get("label") == "Dropdown"]
    buttons = [c for c in detections if c.get("label") == "Button"]
    inputs = [c for c in detections if c.get("label") in ["TextInput", "Input", "SearchInput"]]
    tables = [c for c in detections if c.get("label") == "DataTable"]
    cards = [c for c in detections if c.get("label") == "Card"]

    # =========================================================================
    # RULE 1: Gap between sibling fields in one row, measured against the grid
    # =========================================================================
    # HEURISTIC: Carbon places siblings on grid columns separated by one gutter. A gap of more
    # than one empty column plus two gutters means a field is not sitting on the next column.
    _span, _std, col_w, gutter = calculate_grid_span(0, frame_width, bp_name)
    max_gap = col_w + 2 * gutter
    rows = []  # fields grouped by top edge (within 30 px)
    for c in sorted((c for c in detections if c.get("label") in FIELD_TYPES), key=lambda d: d["bbox"][1]):
        if rows and abs(rows[-1][0]["bbox"][1] - c["bbox"][1]) < 30:
            rows[-1].append(c)
        else:
            rows.append([c])
    for r in rows:
        r.sort(key=lambda d: d["bbox"][0])
    for d1, d2 in [(r[i], r[i + 1]) for r in rows for i in range(len(r) - 1)]:
        gap = d2["bbox"][0] - d1["bbox"][2]
        if gap > max_gap:
            findings.append({
                "issue_id": f"ISSUE-{issue_counter:02d}",
                "defect_id": "DEF-SPACE-02",
                "category": "Excessive Spacing Between Sibling Fields",
                "severity": "Major",
                "affected_components": [d1, d2],
                "evidence": f"Gap between sibling fields is {gap}px; one gutter is {gutter}px and more than {max_gap}px leaves over one empty column",
                "suggested_fix": {
                    "action": f"Move the second field to the next grid column, one {gutter}px gutter after the first",
                    "target_spacing_token": "$spacing-07" if gutter == 32 else "$spacing-05",
                },
            })
            issue_counter += 1

    # =========================================================================
    # RULE 2: Detached Floating Action Button (Apply or Search floating top-right)
    # =========================================================================
    for btn in buttons:
        bx1, by1, bx2, by2 = btn["bbox"]
        # If button is in filter/search area (y1 < 200px) and pushed to far right (> 75% width)
        if by1 < 200 and bx1 > (frame_width * 0.75):
            findings.append({
                "issue_id": f"ISSUE-{issue_counter:02d}",
                "defect_id": "DEF-PROX-02",
                "category": "Detached Floating Action Button",
                "severity": "Major",
                "affected_components": [btn],
                "evidence": f"Action button is floating detached at the page edge (x1={bx1}px) instead of sitting adjacent to filter controls",
                "suggested_fix": {
                    "action": "Move button adjacent to the filter controls with $spacing-05 (16px) margin",
                    "target_spacing_token": "$spacing-05"
                }
            })
            issue_counter += 1

    # =========================================================================
    # RULE 3: Form Input Row Baseline Alignment (e.g. Estimated hours shifted down)
    # =========================================================================
    # Look for inputs/dropdowns in the same logical form row that have mismatched y1
    all_form_controls = inputs + dropdowns
    if len(all_form_controls) >= 2:
        for i in range(len(all_form_controls)):
            for j in range(i + 1, len(all_form_controls)):
                c1 = all_form_controls[i]
                c2 = all_form_controls[j]
                y1_1 = c1["bbox"][1]
                y1_2 = c2["bbox"][1]
                # If they are roughly in the same row area but misaligned vertically by 15-60px
                if 12 < abs(y1_1 - y1_2) < 55 and (c1["bbox"][1] < 450 and c2["bbox"][1] < 450):
                    # Check if they are distinct columns (no large horizontal overlap)
                    if abs(c1["bbox"][0] - c2["bbox"][0]) > 80:
                        findings.append({
                            "issue_id": f"ISSUE-{issue_counter:02d}",
                            "defect_id": "DEF-ALIGN-03",
                            "category": "Misaligned Form Row Baseline",
                            "severity": "Major",
                            "affected_components": [c1, c2],
                            "evidence": f"Form control ({c2.get('label')} at y1={y1_2}px) is vertically shifted below sibling control ({c1.get('label')} at y1={y1_1}px)",
                            "suggested_fix": {
                                "action": f"Align top edge of {c2.get('label')} to y={y1_1}px to maintain consistent form row baseline",
                            }
                        })
                        issue_counter += 1
                        break

    # =========================================================================
    # RULE 4: Mismatched Input vs Dropdown Widths (Search Results Page)
    # =========================================================================
    if len(inputs) >= 1 and len(dropdowns) >= 1:
        for inp in inputs:
            for dd in dropdowns:
                # If both are in top filter row (y < 250px)
                if inp["bbox"][1] < 250 and dd["bbox"][1] < 250:
                    iw = inp["bbox"][2] - inp["bbox"][0]
                    dw = dd["bbox"][2] - dd["bbox"][0]
                    if abs(iw - dw) > 60:
                        findings.append({
                            "issue_id": f"ISSUE-{issue_counter:02d}",
                            "defect_id": "DEF-GRID-04",
                            "category": "Mismatched Filter Input Widths",
                            "severity": "Major",
                            "affected_components": [inp, dd],
                            "evidence": f"Text input width ({iw}px) is significantly smaller than sibling dropdown ({dw}px)",
                            "suggested_fix": {
                                "action": "Ensure text input and dropdown share matching column spans (e.g. lg=5 / ~378px each)",
                                "target_span_lg": 5
                            }
                        })
                        issue_counter += 1
                        break

    # =========================================================================
    # RULE 5: Data Table Full Grid Span (Work Order Page)
    # =========================================================================
    for tbl in tables:
        tx1, ty1, tx2, ty2 = tbl["bbox"]
        tw = tx2 - tx1
        if tw < (frame_width * 0.75):
            findings.append({
                "issue_id": f"ISSUE-{issue_counter:02d}",
                "defect_id": "DEF-GRID-02",
                "category": "Truncated Table Grid Span",
                "severity": "Major",
                "affected_components": [tbl],
                "evidence": f"DataTable occupies only {tw}px ({round(tw/frame_width*100)}% width), squishing columns and leaving empty space on right",
                "suggested_fix": {
                    "action": f"Expand DataTable to span full 16-column grid (lg=16 / {frame_width-32}px) to prevent column truncation",
                    "target_span_lg": 16
                }
            })
            issue_counter += 1

    # =========================================================================
    # RULE 6: Multi-Card Row Span Consistency (Asset Catalog)
    # =========================================================================
    if len(cards) >= 3:
        sorted_cards = sorted(cards, key=lambda c: c["bbox"][0])
        widths = [c["bbox"][2] - c["bbox"][0] for c in sorted_cards]
        if max(widths) - min(widths) > 50:
            findings.append({
                "issue_id": f"ISSUE-{issue_counter:02d}",
                "defect_id": "DEF-GRID-04",
                "category": "Inconsistent Card Column Spans",
                "severity": "Major",
                "affected_components": sorted_cards,
                "evidence": f"Cards in the row have mismatched widths ({min(widths)}px vs {max(widths)}px)",
                "suggested_fix": {
                    "action": "Ensure all 3 cards in the row have equal 5-column spans (lg=5 / ~378px) with 32px gutters",
                    "target_span_lg": 5
                }
            })
            issue_counter += 1

    # Form rules assume a form page. On card-row pages, pills are typed as buttons and card
    # edges match "horizontal line", so the form rules would raise false alarms there.
    card_row = [c for c in cards if c["bbox"][2] - c["bbox"][0] >= 250 and c["bbox"][3] - c["bbox"][1] >= 96]
    if len(card_row) < 2:
        findings.extend(_form_alignment_rules(detections, issue_counter))
    return findings


FIELD_TYPES = ("TextInput", "Dropdown", "NumberInput", "TextArea")


def _form_alignment_rules(detections: list, start_id: int):
    """General form rules. The first row of fields defines the page's columns and right edge.

    7. A field whose left edge matches no column of the first row is off-column.
    8. A field that extends past the first row's right edge overhangs the form.
    """
    tol = 6
    out = []
    n = start_id
    fields = [c for c in detections if c.get("label") in FIELD_TYPES
              and c["bbox"][2] - c["bbox"][0] >= 150]
    form_right = None
    if len(fields) >= 3:
        top_y = min(f["bbox"][1] for f in fields)
        top_row = [f for f in fields if abs(f["bbox"][1] - top_y) <= tol]
        cols = sorted(f["bbox"][0] for f in top_row)
        form_right = max(f["bbox"][2] for f in top_row)
        for f in sorted(fields, key=lambda c: (c["bbox"][1], c["bbox"][0])):
            x1, y1, x2, _ = f["bbox"]
            reasons = []
            nearest = min(cols, key=lambda c: abs(c - x1))
            if abs(nearest - x1) > tol:
                reasons.append(f"left edge x={x1}px matches no column ({', '.join(map(str, cols))})")
            if x2 > form_right + tol:
                reasons.append(f"right edge x={x2}px overhangs the form edge x={form_right}px")
            if reasons:
                out.append({
                    "issue_id": f"ISSUE-{n:02d}",
                    "defect_id": "DEF-ALIGN-01",
                    "category": "Field Off Column Grid",
                    "severity": "Major",
                    "affected_components": [f],
                    "evidence": "; ".join(reasons),
                    "suggested_fix": {"action": f"Snap the field to the column starting at x={nearest}px and keep it inside x={form_right}px"},
                })
                n += 1

    return out


# components.json (normalize_detections.py) uses "Tile"; the rules below say "Card".
TYPE_ALIASES = {"Tile": "Card"}


def components_to_detections(data: dict):
    """Adapt components.json (normalize_detections.py) to the shape the rules expect."""
    dets = [
        {
            "id": c["id"],
            "label": TYPE_ALIASES.get(c["carbon_type"], c["carbon_type"]),
            "bbox": [round(v) for v in c["box_design_px"]],
            "confidence": c["confidence"],
        }
        for c in data["components"]
        if c.get("carbon_type")
    ]
    dim = {
        "width": round(data.get("frame_width_design_px", data["image"]["width_px"])),
        "height": round(data.get("frame_height_design_px", data["image"]["height_px"])),
    }
    return dets, dim


def to_issues(findings: list):
    """Issue list in the shape annotate_image.py reads (lowercase severity, component ids)."""
    return [
        {
            "issue_id": f["issue_id"],
            "defect_id": f["defect_id"],
            "category": f["category"],
            "severity": f["severity"].lower(),
            "affected_component_ids": [c["id"] for c in f["affected_components"] if "id" in c],
            "evidence": f["evidence"],
            "suggested_fix": f["suggested_fix"],
        }
        for f in findings
    ]


def run_analysis_on_file(detections_json_path: str, output_findings_path: str = None):
    if not os.path.exists(detections_json_path):
        print(f"Error: {detections_json_path} not found.")
        return

    with open(detections_json_path, "r") as f:
        data = json.load(f)

    if "components" in data:
        detections, dim = components_to_detections(data)
    else:
        detections = data.get("detections", [])
        dim = data.get("dimensions", {"width": 1312, "height": 738})
    img_w = dim.get("width", 1312)
    img_h = dim.get("height", 738)

    print(f"Analyzing {len(detections)} components for {data.get('image')}...")
    findings = analyze_layout(detections, frame_width=img_w, frame_height=img_h)

    report = {
        "image": data.get("image"),
        "dimensions": dim,
        "total_components": len(detections),
        "total_issues": len(findings),
        "findings": findings,
        "issues": to_issues(findings),
    }

    if not output_findings_path:
        output_findings_path = os.path.splitext(detections_json_path)[0] + "_findings.json"

    with open(output_findings_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Found {len(findings)} layout placement issues.")
    print(f"Saved findings report to: {output_findings_path}")
    return report

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "create_work_order_detections.json"
    run_analysis_on_file(src, sys.argv[2] if len(sys.argv) > 2 else None)
