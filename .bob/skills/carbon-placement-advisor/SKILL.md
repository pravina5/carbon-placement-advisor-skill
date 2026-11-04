---
name: carbon-placement-advisor
description: Use when the user wants a placement or layout review of a UI screenshot or Figma frame against the Carbon Design System, asks where components should go, whether a layout is correct, or mentions SAM 3, component detection, grid alignment, spacing tokens or misplaced buttons, fields, cards and tabs. Runs SAM 3 locally on the image, measures positions, and reports every placement problem with a suggested fix. Not for turning a Figma design into code (use figma or carbon-figma-analysis).
---

# Carbon placement advisor

Reviews where components sit in a UI image and says what to move. SAM 3 finds shapes, scripts measure them, and you explain the result. Everything runs on this Mac. Nothing is uploaded.

Requires Agent mode, because the scripts are run with `execute_command`.

## Honesty rules (read first)

- Report every problem found, not just one. Report nothing the scripts did not measure.
- Never claim a component that was not detected. List what could not be detected.
- Component types are inferred from shapes and geometry. State the confidence. Types with `low_confidence: true` get hedged wording.
- A rule marked heuristic in [`references/placement-rules.md`](references/placement-rules.md) or [`references/defect-taxonomy.md`](references/defect-taxonomy.md) is a hint. Say so, and ask a designer to confirm.
- Without a good reference version of the page, the intended layout is unknown. Hedge ("appears", "possibly").
- If Figma MCP or SAM 3 is unavailable, say so. Do not guess a review from the picture alone.

## Workflow

Run the scripts from `.bob/skills/carbon-placement-advisor/scripts/`. Use the project's virtual environment Python (usually `../../../../.venv/bin/python`).

1. **Check the environment** once per session.
   `python check_env.py`
   If it prints NOT READY, show the FAIL lines and stop. Point the user to [README.md](README.md). Never ask for a HuggingFace token. The user runs `hf auth login` themselves.

2. **Get the image and its scale.**
   - User image: use the path they give.
   - Figma URL: export one frame with `figma-mcp` `get_screenshot`, and read the frame width with `get_metadata`.
   - Ask for the **frame width in design px** and the **export scale** (1 for @1x, 2 for @2x) if they are unknown. Do not assume. One of the two is required.

3. **Run the review** (about 1 minute; the first run may download about 5 GB of weights).
   `python run_review.py --image <image> --output-dir <workspace>/placement-reviews/<name> --frame-width <px>`
   Add `--export-scale 2` for @2x images. The command prints a JSON summary and writes `detections.json`, `components.json`, `findings.json` and `annotated.png`. The `placement-reviews/` folder is git-ignored.

4. **Read the results.**
   - `findings.json`: the `issues` list (`ISSUE-NN`, `defect_id`, severity, `affected_component_ids`, `evidence`, `suggested_fix`).
   - `components.json`: the inventory, with `carbon_type`, `confidence` and `type_evidence`.
   - `annotated.png`: open it with `read_file` and check that the numbered markers sit on the right components.
   - `warnings` in the summary: relay each one (for example `scale_derived`, `tabs_not_split`).

5. **Add judgment only where the rules allow it.** Look at the image for problems the scripts cannot measure (for example wrong component for the job). Label those as judgment, not measured.

6. **Write the review** using [`references/report-template.md`](references/report-template.md). Give every issue its number from the annotated PNG.

7. **Stop and ask** whether the user wants changes explained further. Do not edit their designs.

## What the scripts can and cannot do

Detected types: Button, Tag, Checkbox, Dropdown, TextInput, NumberInput, TextArea, Tab (selected and unselected), Tile (a card), Icon.

Known limits, say these when relevant:
- A TextInput and a Dropdown look identical when the Dropdown has no chevron. Such a field is reported as TextInput.
- TextArea is guessed from the empty space above a field. NumberInput needs both a plus and a minus sign.
- Unselected tab edges are estimated midway between the counted labels.
- Several layout rules were written for Work Order and Asset Catalog style pages and may not apply to other pages.
- Tuning used five screens, so accuracy on new pages is unproven.

## Failure handling

| Symptom | What to do |
|---|---|
| `check_env.py` says NOT READY | Show the failed lines, point to the README, stop |
| Exit 3 | The user has no approved access to `facebook/sam3`. They must request access and run `hf auth login` |
| Exit 4 | Weights missing or no network. Check the connection and 5 GB of disk |
| Exit 2 | Bad input (missing scale, wrong file type). Fix the command |
| `no_components` warning | Nothing could be typed. Say the detector found nothing usable and do not review |
| Many `leftovers` in `components.json` | Mention that some shapes were detected but not typed |

## References (read only when needed)

- [`references/placement-rules.md`](references/placement-rules.md): Carbon grid, spacing tokens, alignment rules.
- [`references/defect-taxonomy.md`](references/defect-taxonomy.md): defect ids, severity, fixes.
- [`references/component-prompts.md`](references/component-prompts.md): which SAM 3 prompts work and which failed.
- [`references/annotation-schema.md`](references/annotation-schema.md): file formats.
- `carbon-figma-analysis` and `carbon-image-analysis`: use these instead when the user wants exact Figma node data or a component build spec rather than a placement critique.
