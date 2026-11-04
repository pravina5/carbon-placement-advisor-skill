# Plan: SAM 3 powered Carbon placement advisor skill for Bob

## Top-level overview

**Goal.** Create a Bob skill (working name `carbon-placement-advisor`) that takes a Figma frame (or any UI screenshot), uses Meta's SAM 3 (via [`sam3-mac`](https://github.com/benreichman/sam3-mac)) to detect and segment UI components from the pixels, and then suggests better placement of those components against the Carbon Design System (16-column lg grid, spacing tokens, layering, hierarchy).

**Confirmed decisions**
| Topic | Decision |
|---|---|
| Design system | Carbon only. Reuse rules already documented in `carbon-figma-analysis`, `carbon-image-analysis`, `carbon-styling-practices` |
| SAM 3 role | SAM 3 only. Every design, including Figma, is treated as an image. Figma MCP (`figma-mcp`) is used only to export a screenshot and read the frame width/height needed for px to grid mapping |
| Training data | Paired corpus. Each sample is one good design plus deliberately broken variants (misaligned, wrong spacing, wrong component, wrong hierarchy), each exported as PNG plus annotation JSON |
| Output | Markdown placement review (issues, severity, suggested move with Carbon grid spans and spacing tokens) plus an annotated PNG with detected boxes |
| Testing | Evals, with-skill versus without-skill, on held-out designs |

**Key facts that shape the approach (evidence-based)**
- Bob cannot be fine-tuned. "Teaching" Bob means a curated, labeled example corpus plus explicit rules stored in the skill's `references/` folder that Bob reads as few-shot guidance, with a deterministic script doing the geometry.
- `sam3-mac` runs SAM 3 on Apple Silicon (MPS) or CPU. `processor.set_text_prompt(<noun phrase>, state)` returns `boxes` (N,4 pixel coords), `scores`, and `masks` per prompt. Short concrete noun phrases work best. Multiple prompts can reuse one encoded image.
- SAM 3 is prompted by text and is not UI-trained. It returns *regions for a phrase*, not Carbon component types. Mapping regions to Carbon component names is therefore our responsibility (prompt vocabulary plus classification rules) and is the largest technical risk. Sub-task 1 is a feasibility gate for this.
- SAM 3 weights (~3.5 GB) are gated on HuggingFace (`facebook/sam3`), need an approved account and token, and the library targets Python 3.12.
- No existing skill bundles a venv. Convention is `scripts/requirements.txt` plus `python3` or `uv run --no-project --python 3.12 --with ...`. Figma MCP server id is `figma-mcp` (`~/.bob/settings/mcp.json`, `http://127.0.0.1:3845/mcp`).
- Existing overlap: `carbon-image-analysis` already estimates components and grid spans heuristically (no segmentation). The new skill differs by adding measured pixel detections and a placement critique. Reuse its assessment vocabulary rather than duplicating it.
- Carbon facts to reuse: lg 16 columns / 1584px max grid / 32px gutter, md 8 columns, sm 4 columns; spacing tokens `$spacing-01` (2px) to `$spacing-13` (160px); span formula `ceil(width / (gridWidth / columns))`.

**Approach in one view**
1. Define a defect taxonomy and rules (what is "good" and "bad" in Carbon terms).
2. Build a Figma sample kit and create a paired good/bad corpus with ground-truth annotations.
3. Build scripts: SAM 3 detection, then normalization into a component list, then deterministic layout analysis, then annotated PNG.
4. Write the skill: SKILL.md workflow plus references with curated examples.
5. Evaluate on held-out designs and iterate; optimize the description; package and install.

**Non-goals.** No fine-tuning of SAM 3 or Bob. No code generation of the redesigned UI. No non-Carbon design systems. No automatic edits back into Figma.

---

## Proposed skill layout (created in workspace, not inside `.bob`)

```
carbon-placement-advisor/
├── SKILL.md                      workflow, when to use, output template, failure handling
├── scripts/
│   ├── requirements.txt          pinned deps (torch, sam3, sam3-mac and the transitive list)
│   ├── check_env.py              verifies python version, device, HF auth, weights present
│   ├── detect_components.py      SAM 3 runner: image + prompt list -> raw detections JSON
│   ├── normalize_detections.py   dedupe, overlap resolution, classify to Carbon component guess
│   ├── analyze_layout.py         px -> grid spans, spacing tokens, alignment/grouping checks
│   └── annotate_image.py         draws boxes, labels, issue markers -> annotated PNG
├── references/
│   ├── placement-rules.md        the good-placement rules in Carbon terms
│   ├── defect-taxonomy.md        bad-placement categories, severity, how each is detected
│   ├── component-prompts.md      SAM 3 prompt vocabulary per Carbon component and known failures
│   ├── annotation-schema.md      JSON schema for corpus labels
│   ├── report-template.md        markdown review structure
│   └── examples/                 small curated good/bad pairs used as few-shot (PNG + JSON + note)
└── evals/evals.json
```
The full corpus (larger) lives outside the skill in a sibling `placement-corpus/` folder; only a curated subset is shipped in `references/examples/` to keep the skill small and progressive.

---

## Sub-task 1 — Feasibility spike and environment for SAM 3 on this Mac

**Intent.** Prove SAM 3 can produce useful UI regions before investing in a corpus. Fail early if prompt-based detection cannot find UI components well enough.

**Expected outcomes**
- A reproducible local environment where `sam3-mac` runs on MPS or CPU.
- A written go/no-go finding: per-prompt recall and box quality on 3 to 5 hand-picked Carbon screens (button, text input, data table, card/tile, header, side navigation, modal, tabs).
- A list of prompts that work, prompts that fail, and proposed fallbacks (for example, detect a coarse region such as "section" and sub-classify by geometry).

**Todo list**
1. Request and confirm access to `facebook/sam3` on HuggingFace; authenticate with a read-only token via `hf auth login` or an environment variable. Never commit the token; add a `.gitignore`.
2. Create a Python 3.12 venv; install latest stable `torch`/`torchvision`, then SAM 3 from source and `sam3-mac`, following the repo's README order.
3. Before pinning, verify each package is actively maintained (activity within 6 months), check licenses, and scan for known vulnerabilities per the security rules. Record any deviations.
4. Run the README example on a UI screenshot with a handful of prompts; record time per image and device.
5. Export 3 to 5 Carbon-based Figma frames to PNG via `figma-mcp:get_screenshot` (note the scale factor) and run a prompt sweep.
6. Compare detections against known Figma layers by IoU to get initial recall numbers per prompt.
7. Write findings (including a go/no-go and fallback strategy) into `references/component-prompts.md` draft.

**Relevant context**
- `https://github.com/benreichman/sam3-mac` (install order, API, limitations, troubleshooting)
- `~/.bob/skills/carbon-figma-analysis/SKILL.md` (Figma MCP tool usage)
- `~/.bob/settings/mcp.json` (`figma-mcp` server)

**Status** `[ ] pending`

---

## Sub-task 2 — Define the placement standard: rules, defect taxonomy, annotation schema

**Intent.** Decide, in writing, what "good" and "bad" mean so that corpus labels, scripts, and Bob's advice all agree. This is the core of what Bob learns.

**Expected outcomes**
- `placement-rules.md`: concise Carbon-grounded rules for good placement.
- `defect-taxonomy.md`: bad-placement categories, each with id, definition, severity (blocker, major, minor), how it is detected (geometric check, classification check, or human-only), and the recommended fix pattern.
- `annotation-schema.md`: the JSON contract for every corpus sample.

**Proposed defect categories (to be confirmed during this sub-task)**
| Category | What is wrong | Example variant to create |
|---|---|---|
| Grid misalignment | Edges/spans do not snap to the 16/8/4 column grid or gutters | Card shifted 10px off column edge; span of 5 where 4 or 6 is required |
| Spacing violation | Gaps not on the `$spacing-*` scale or inconsistent between siblings | 13px and 21px gaps in a form |
| Alignment | Siblings not sharing left edge, baseline, or center | Labels and inputs with staggered x positions |
| Grouping / proximity | Related items far apart, unrelated items close | Label detached from its input; two form groups touching |
| Visual hierarchy | Primary action not dominant or not in the expected position | Primary and secondary buttons swapped; primary button far from form |
| Wrong component | A component used for the wrong job | Radio buttons for 12 options; link styled as button for a submit action; modal for a long form |
| Wrong placement for component pattern | Component in a non-conventional zone | Page title below content; global header content inside the page body; pagination above the table |
| Layering / surface | Nested surfaces with no layer distinction, or wrong layer | Card on same background token as the page |
| Responsive breakpoint fit | Layout that cannot reflow to md/sm | Four-up layout with fixed widths and no stacking |
| Density and touch target | Controls smaller than Carbon sizes or crowded | 24px-high input in a default-size form |
Only rules that Carbon documentation or the existing carbon-* skills support are kept; anything else is marked "heuristic" so Bob states lower confidence.

**Todo list**
1. Collect the authoritative Carbon rules from existing skills (`carbon-styling-practices`, `carbon-workflow-practices`, `carbon-figma-analysis/references/grid-calculation.md`, `layer-detection.md`) and the Carbon site via `carbon-builder` guidance; cite sources in each rule.
2. Draft the rules and taxonomy; mark each rule as `measurable` (script can check), `inferable` (needs component classification), or `judgment` (Bob reasons from examples).
3. Define the annotation JSON schema (conceptual fields): sample id, pair id, role (`good` or `broken`), source Figma file/node, frame size and export scale, breakpoint, pattern type, list of components (Carbon type, bbox, grid span, parent group), list of defects (category id, severity, affected component ids, expected fix with target span/token), and free-text rationale.
4. Define naming conventions (see Sub-task 3) so ground truth can be read from Figma layer names.
5. Review the standard with a Carbon-aware designer before the corpus is built, and freeze version 1.

**Relevant context**
- `~/.bob/skills/carbon-figma-analysis/references/{grid-calculation,layer-detection,assessment-template,design-fidelity}.md`
- `~/.bob/skills/carbon-styling-practices/SKILL.md`, `carbon-workflow-practices/SKILL.md`, `carbon-image-analysis/SKILL.md`
- Spacing scale and breakpoints listed in the Top-level overview

**Status** `[ ] pending`

---

## Sub-task 3 — Figma sample kit: how someone builds the sample designs

**Intent.** Give the person creating sample designs (designer or non-designer) a repeatable method, so output is consistent and annotations can be derived from the Figma file rather than drawn by hand.

**Expected outcomes**
- A one-page "How to build a sample" guide and a Figma template file/page structure.
- A coverage matrix of page patterns and defect categories to guarantee balanced data.
- A naming convention that makes each Figma layer self-labelling.

**Figma template structure**
- One Figma file per pattern family; one page per sample; on each page a row of frames: `GOOD` followed by `BAD-<category>-<n>` variants, all at identical frame size (lg 1584 wide, plus md 672/sm 320 for a subset).
- Frames start from the Carbon Figma kit with the Carbon grid overlay enabled. Layer names follow `<CarbonComponent>/<variant>/<role>` (for example `Button/primary/submit`, `TextInput/default/email`, `DataTable/default/orders`). Groups use `Group/<purpose>`.
- Each BAD frame is created by duplicating the GOOD frame and applying exactly one deliberate defect (single-defect variants), plus a few multi-defect variants for realism. A description plate in the Figma page (outside the frame) states the defect and the expected fix.
- Keep the non-visual information (notes, rationale) in a sibling text layer so it never appears in exported pixels that SAM 3 sees.

**Coverage matrix (target patterns)**
Dashboard overview, list/data table page, create/edit form, settings page, detail page with tabs, login/sign-in, modal/dialog flow, empty state/onboarding, search results, side-panel/filter pattern. Each pattern needs at least one good design and a broken variant for each applicable defect category, at lg and a subset at md/sm.

**Todo list**
1. Write the sample-building guide (steps, naming rules, "one defect per variant", what not to do such as flattening layers or rasterizing).
2. Prepare the Carbon Figma template page (grid overlay, token styles, instance naming).
3. Produce the coverage matrix as a checklist file in `placement-corpus/coverage.md`.
4. Define the done criteria for a sample (named layers, frame size, annotation present, rationale present, reviewed).
5. Pilot with 2 patterns end to end and adjust the guide based on friction.

**Relevant context**
- Carbon grid overlay and token specs (Top-level overview)
- `figma-mcp` read tools: `get_metadata`, `get_screenshot`, `get_variable_defs`

**Status** `[ ] pending`

---

## Sub-task 4 — Build the labeled corpus (good versus bad pairs)

**Intent.** Produce the data Bob learns from: each good design is paired with broken variants, with exact labels, so Bob sees the same content placed correctly and incorrectly.

**Expected outcomes**
- A folder per pattern containing, for each frame: exported PNG, annotation JSON, and a short human note.
- Ground-truth annotations auto-derived from Figma (component types from layer names, bboxes and spans from metadata) with defect labels added from the variant plate.
- A split: `reference` (used as few-shot examples inside the skill), `calibration` (used to tune prompts and thresholds), and `held-out` (never shown to Bob in references; used only for evals).

**Todo list**
1. Build the samples per the coverage matrix, starting with the 2 pilot patterns, then expanding.
2. Write a small extraction script (corpus tooling, not shipped in the skill) that, per frame, calls `figma-mcp:get_metadata` and `get_screenshot`, writes the PNG and a skeleton annotation JSON (components, bboxes, grid spans).
3. Add defect labels and expected fixes (target span, token, new position) manually, pair good and broken via `pair id`.
4. Validate: schema check, every BAD sample has at least one defect, every GOOD sample has none, pair frames share size and content, and layer names resolve to known Carbon components.
5. Assign splits by pattern (hold out entire patterns where possible, not just variants, to test generalization). Keep roughly half of patterns' variants for reference and the remainder for calibration/held-out.
6. Select a small curated set (for example 6 to 10 pairs spanning all defect categories) to ship in `references/examples/` with a one-paragraph "why good / why bad" note each.
7. Review annotation quality with a second reviewer on a sample of the corpus; fix disagreements and record the final rules in the taxonomy.

**Relevant context**
- Schema from Sub-task 2; template and naming from Sub-task 3
- `placement-corpus/` (new sibling folder; not inside the skill)

**Status** `[ ] pending`

---

## Sub-task 5 — Detection pipeline: SAM 3 runner and component normalization

**Intent.** Turn pixels into a clean list of Carbon-typed component boxes that the layout analysis can use.

**Expected outcomes**
- `detect_components.py`: runs a configurable prompt list per image, outputs raw detections (prompt, box, score, mask area) as JSON, supports MPS/CPU auto-selection, a confidence threshold, and clear errors for missing weights/auth.
- `normalize_detections.py`: removes duplicates and nested/overlapping detections, merges prompt hits, assigns a best-guess Carbon component type and a confidence, and records unlabeled leftovers.
- Measured detection quality against the calibration split: recall, precision, and mean IoU per component type, with the tuned prompt list and thresholds written to `component-prompts.md`.

**Todo list**
1. Define the prompt vocabulary per Carbon component from Sub-task 1 findings, with fallbacks (coarse region prompt then geometric sub-classification).
2. Implement the runner reusing one image encoding for many prompts, and a mode that downsizes very large images safely.
3. Implement normalization: non-max suppression across prompts, containment rules (child versus parent), and type classification rules (aspect ratio, size relative to Carbon sizes, text presence if available).
4. Run on the calibration split; compute the metrics against ground truth; tune prompts and thresholds; record weak classes and mark them "low confidence" in references.
5. Implement `annotate_image.py` to draw boxes, type labels, confidence, and issue markers with numbered callouts matching the markdown report.
6. Handle errors: no detections, too many detections, weights not available, and image scale unknown (ask for frame width).

**Relevant context**
- `sam3-mac` API: `install()`, `build_image_model()`, `set_image()`, `set_text_prompt()`; outputs `boxes`, `scores`, `masks`
- Calibration split from Sub-task 4

**Status** `[ ] pending`

---

## Sub-task 6 — Layout analysis and suggestion engine

**Intent.** Compare the detected layout with the placement rules and propose concrete moves in Carbon terms. Deterministic checks go in code; judgment calls are left to Bob using the examples.

**Expected outcomes**
- `analyze_layout.py` converts boxes to design pixels using the frame width and export scale, maps widths to grid spans (`ceil(width / (gridWidth / columns))` for sm/md/lg), maps gaps to the nearest `$spacing-*` token, and flags: off-grid edges, inconsistent sibling gaps, misaligned edges, grouping/proximity anomalies, and out-of-zone placement for known patterns.
- Output is structured findings: issue id, category, severity, affected components, evidence (measured values), and a suggested fix (target span at sm/md/lg, token, new relative position).
- Measured agreement with the corpus: for the calibration split, the fraction of labeled defects found (recall) and the fraction of reported issues that are real (precision).

**Todo list**
1. Implement the measurable rules from `placement-rules.md` first (grid, spacing, alignment), then inferable rules (grouping, hierarchy, zones) that rely on component types.
2. Define confidence handling: lower-confidence component types lead to hedged findings rather than hard claims.
3. Generate suggested placements as concrete targets (for example "move X to span lg=6 starting at column 1; change gap from 13px to `$spacing-05` 16px").
4. Test on pairs: the GOOD frame should report no major issues; each BAD variant should report its labelled defect category.
5. Record false positives and false negatives; adjust thresholds or demote rules to `judgment`.

**Relevant context**
- Grid/spacing facts in Top-level overview; `carbon-figma-analysis/references/grid-calculation.md`
- Defect taxonomy from Sub-task 2

**Status** `[ ] pending`

---

## Sub-task 7 — Author the skill (SKILL.md and references)

**Intent.** Package the workflow so Bob knows when and how to run the pipeline, how to use the examples as guidance, and how to present the result.

**Expected outcomes**
- A `SKILL.md` (under 500 lines) with a "pushy" description (no colons in the description field) that triggers on placement/layout critique, Figma frames, screenshots, SAM, segmentation, and Carbon layout review.
- Workflow in `SKILL.md`: (1) check environment with `check_env.py`; (2) obtain image (Figma URL via `figma-mcp:get_screenshot`, or user image) and the frame width/scale; (3) run detection; (4) normalize; (5) analyze layout; (6) read the relevant `references/examples/` pairs for the detected pattern and defect categories; (7) write the markdown review and the annotated PNG; (8) pause for user confirmation before any further action.
- Output template in `references/report-template.md`: summary, component inventory with confidence, numbered issues (category, severity, evidence, suggested move with sm/md/lg spans and spacing tokens, "why" referencing a good example), what looks correct, assumptions and limitations.
- Rules for honesty: state confidence, do not invent components that were not detected, list undetected regions, and say when SAM 3 or Figma MCP is unavailable rather than guessing.

**Todo list**
1. Initialize the skill folder at the workspace location using `scripts/init_skill.py` from skill-creator (do not create it inside `.bob`).
2. Write frontmatter (name, description, tags, `connections: figma`, compatibility notes for Python 3.12 and HF access) and the body workflow.
3. Move rules, taxonomy, prompts, and schema into `references/` with clear pointers on when to read each; add a table of contents to any file over 300 lines.
4. Add the curated example pairs with notes; explain in SKILL.md how Bob should use a "good versus bad" pair as reference when giving advice.
5. Document setup (HF token, weights download, first-run time, disk space) and failure handling.
6. Cross-reference `carbon-figma-analysis` and `carbon-image-analysis` to avoid duplicated guidance and to define when to prefer each.

**Relevant context**
- `~/.bob/skills/skill-creator/SKILL.md` and `references/` (frontmatter rules, progressive disclosure)
- Existing Carbon skills for tone and structure

**Status** `[ ] pending`

---

## Sub-task 8 — Evals on held-out designs

**Intent.** Prove the skill improves Bob's placement advice and find where it fails, using designs Bob has never seen in references.

**Expected outcomes**
- `evals/evals.json` with prompts over held-out designs (good and broken), each with verifiable expectations.
- A with-skill versus without-skill comparison, benchmark, and review report per skill-creator's testing workflow.
- Iteration notes and a measurable improvement or a documented decision.

**Eval design**
- Prompt styles: "Review this Figma frame for placement problems", "Where should these components go?", "Is this layout correct?" (on a GOOD frame, to test false positives), and a screenshot-only prompt (no Figma).
- Expectations (verifiable): names the expected defect category; identifies the affected component; gives a target span and token consistent with ground truth; does not flag a GOOD frame with major issues; includes confidence/limitations; produces annotated PNG with boxes.
- Metrics: defect recall, false-positive rate on GOOD frames, span/token correctness of suggestions, component-type accuracy, and a qualitative reviewer score.
- Baselines: without_skill (Bob alone looking at the image) versus with_skill.

**Todo list**
1. Select held-out frames (entire patterns not used in references) and write 8 to 12 evals spanning all defect categories, plus GOOD controls.
2. Run per skill-creator `references/testing-workflow.md` and the Bob platform reference (`platform-bob-orchestrator.md` when `new_task` is available, otherwise `platform-bob-fallback.md`) in a sibling `carbon-placement-advisor-workspace/`.
3. Grade outputs with `grading.json` (fields `text`, `passed`, `evidence`), aggregate the benchmark, and review with the user.
4. Analyze failures: detection problem (Sub-task 5), rule problem (Sub-task 6), or guidance problem (Sub-task 7); fix the right layer and rerun.
5. Expand the test set once results stabilize.

**Relevant context**
- `~/.bob/skills/skill-creator/references/{testing-workflow,schemas,platform-bob-orchestrator}.md`, `agents/grader.md`

**Status** `[ ] pending`

---

## Sub-task 9 — Description optimization, packaging, installation

**Intent.** Make the skill trigger reliably and ship it.

**Expected outcomes**
- Tuned description verified against should-trigger and should-not-trigger prompts (including near-misses such as pure Figma-to-code requests that belong to `figma`/`carbon-figma-analysis`).
- A `.skill` package and, if the user approves, a copy in `~/.bob/skills/`.

**Todo list**
1. Run skill-creator's description improvement loop (`scripts/run_loop.py`/`improve_description.py`) with a balanced prompt set.
2. Validate with `scripts/quick_validate.py`; package with `scripts/package_skill.py`.
3. Ask the user whether to install globally, keep local, or both.
4. Write a short maintenance note: how to add new corpus samples and re-run calibration and evals.

**Relevant context**
- `~/.bob/skills/skill-creator/scripts/`

**Status** `[ ] pending`

---

## Risks and open questions

| Risk | Impact | Mitigation |
|---|---|---|
| SAM 3 text prompts may not reliably isolate UI components (it is not trained for UI) | Detection quality caps the whole skill | Sub-task 1 go/no-go; coarse-region plus geometric sub-classification fallback; calibrate with the corpus |
| Component *type* is not given by SAM 3 | Wrong-component defects cannot be reliably detected | Mark as `judgment`/low confidence; use the corpus to learn which types are distinguishable |
| Pixel-only input loses Figma metadata that is exact | Less precise than node-based analysis | Accepted by user choice; the corpus uses Figma as ground truth to measure the gap; frame width from Figma MCP is the only metadata used |
| Gated weights, large download, and Mac-specific shim | Setup friction, brittle upgrades | `check_env.py`, pinned versions, documented setup, security review of dependencies |
| Small, synthetic corpus can bias Bob toward artificial defects | Over/under-flagging on real screens | Realistic variants, multiple patterns, held-out patterns, option to add real production screens later |
| Screenshot scale (@1x/@2x) ambiguity | Wrong px to token mapping | Always record export scale and frame width; ask the user if unknown |

## Security notes for implementation
- Keep the HuggingFace token in `hf auth login` storage or an environment variable; never in files; create `.gitignore` covering `.venv`, caches, tokens, and large weights.
- Use the latest stable, actively maintained dependencies (verify before pinning) and keep a lock/requirements file.
- The skill runs locally only; it must not start any network service (no binding to `0.0.0.0`). Use HTTPS for any download.
- Screenshots of unreleased designs stay local; do not upload them to external services.

---

## Ownership: who does what

Legend: **You** = human (designer/PM), **Bob** = Bob in Agent mode (can run commands and write files), **Both** = Bob drafts, you review/approve.

| Sub-task | You | Bob |
|---|---|---|
| 1. Feasibility spike | Request access to `facebook/sam3` on HuggingFace, create the read-only token, run `hf auth login` yourself (secret, must not pass through Bob). Choose the 3 to 5 Carbon Figma frames to test. Judge the go/no-go | Create the venv, install `torch`, SAM 3, `sam3-mac`; run the prompt sweep; compute IoU/recall; write the findings |
| 2. Rules, taxonomy, schema | Final decision on what is good or bad in Carbon (a Carbon-aware designer reviews and freezes v1) | Draft rules from the existing carbon-* skills with citations, taxonomy, and annotation schema |
| 3. Figma sample kit | **Create the actual Figma designs** (good frames and broken copies) following the guide | Write the "how to build a sample" guide, naming convention, coverage checklist |
| 4. Corpus | Build the Figma samples; write the defect label and expected fix for each broken frame; review quality | Write the extraction script; export PNGs and skeleton JSON from Figma via `figma-mcp`; validate schema and pairs; assign splits; pick the curated examples |
| 5. Detection pipeline | Review calibration metrics | Write and tune `detect_components.py`, `normalize_detections.py`, `annotate_image.py` |
| 6. Layout engine | Decide which rules to demote to "judgment" when false positives appear | Write `analyze_layout.py`; run against paired samples; report false positives/negatives |
| 7. Author the skill | Review wording and examples | Write `SKILL.md`, references, report template |
| 8. Evals | Approve expectations; review the eval report | Write evals, run with/without skill, grade, aggregate, propose fixes |
| 9. Package | Choose global install or local | Run validation and packaging, optimize description |

## Where the Figma designs and screenshots live

- **Figma designs are not generated by Bob or SAM 3.** A person builds them in Figma (Sub-task 3 and 4). I have not verified that the Figma MCP in your setup can create designs, and the plan does not depend on it.
- The **Figma file stays the source of truth**. Bob exports from it using the read tools of `figma-mcp` (`get_screenshot`, `get_metadata`).
- The exported files are **stored in a folder** (`placement-corpus/`) as PNG + annotation JSON per frame. That folder is the training data. A small curated subset is copied into the skill's `references/examples/`, which is what Bob reads as reference when it gives advice.
- **At skill run time** on a new design, no corpus is processed. Bob gets a screenshot of that one design, runs SAM 3 on it, and compares the result with the rules and the few curated examples.

## How SAM 3 and the Bob skill connect

SAM 3 is not an MCP server or a Bob feature. It is a local Python process that the skill starts.

```
User gives Figma URL or screenshot
  -> Bob loads the skill (SKILL.md instructions)
  -> Bob exports PNG (figma-mcp get_screenshot) or uses the user's image
  -> Bob runs: python scripts/detect_components.py <image> --prompts ...   (execute_command)
        SAM 3 via sam3-mac on MPS/CPU -> writes detections.json
  -> Bob runs: normalize_detections.py -> analyze_layout.py -> annotate_image.py
  -> Bob reads findings JSON and references/examples, then writes the markdown review
  -> Bob shows the annotated PNG
```

- **Contract between SAM and Bob = files.** Image in, `detections.json` out. Bob never imports SAM; scripts do.
- **Requires Agent mode** (command execution). Plan mode cannot run the scripts.
- **Alternative (not planned, only if needed later):** wrap SAM 3 as a local MCP server so the model stays loaded between calls. This avoids the 6s+ model load per run but adds a server to maintain. Start with scripts.
