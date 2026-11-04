# carbon-placement-advisor

A Bob skill that looks at a UI screenshot or Figma frame and tells you where components are placed badly, with a suggested fix for each problem. It uses Meta's SAM 3 model (through [sam3-mac](https://github.com/benreichman/sam3-mac)) to find shapes, scripts to measure them, and Carbon Design System rules to judge them.

Everything runs on your Mac. Your designs are not uploaded anywhere.

## What it does, in plain words

1. You give Bob a screenshot (or a Figma link) and the frame width.
2. SAM 3 finds shapes in the picture: buttons, fields, tabs, cards, checkboxes.
3. A script decides what Carbon component each shape is (for example "a field with a chevron is a Dropdown").
4. Another script measures positions and checks them against the rules (alignment, widths, button placement).
5. Bob writes a review listing **every** problem, and gives you a copy of the image with numbered markers on each one.

SAM 3 does not know Carbon. It only finds shapes. The "which component is this" step is our own logic, and it can be wrong. The review always says how confident it is.

## Before you start: what you need (please confirm each one)

| # | You need | How to check |
|---|---|---|
| 1 | A Mac. Apple Silicon is best (uses the built-in GPU, called MPS). | Apple menu > About This Mac |
| 2 | **Python 3.12** (3.10 or newer may work; SAM 3 officially targets 3.12) | `python3.12 --version`. Install with `brew install python@3.12` |
| 3 | About **5 GB free disk** for the model weights, plus about 1.5 GB for the Python environment | Finder > Get Info on your disk |
| 4 | A **HuggingFace account** that has been **approved** for the gated model `facebook/sam3` | Open https://huggingface.co/facebook/sam3 and request access. Approval is not instant |
| 5 | A HuggingFace **read-only token**, which you save by running `hf auth login` yourself | See step 4 below. Never paste the token into Bob, a file or a chat |
| 6 | Bob in **Agent mode** (the scripts are run as commands) | Bob mode selector |
| 7 | *Optional:* the Figma MCP server (`figma-mcp`) running, if you want to give Bob a Figma link instead of an image | Bob settings > MCP |
| 8 | The frame width in Figma (px) and the export scale (1 for @1x, 2 for @2x) | Figma: select the frame; export panel |

No CUDA, no Xcode, and no GPU driver are needed.

## Install

The `.venv` folder is **not** shared. It is listed in `.gitignore` because it is 1.2 GB and specific to one machine. Everyone who uses the skill creates their own, with the steps below. The exact versions are pinned in [`scripts/requirements.txt`](scripts/requirements.txt), so every machine gets the same setup.

Run these in the project root (the folder that contains `.bob/`).

```bash
# 1. Create and enter a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 2. PyTorch (macOS wheels include MPS support)
pip install torch torchvision

# 3. SAM 3, at the exact commit this skill was tested with
pip install "git+https://github.com/facebookresearch/sam3.git@f1647e8d0c1d280991f4d1b7d974c2704537fe66"

# 4. sam3-mac (not on PyPI), at the exact commit this skill was tested with
pip install "git+https://github.com/benreichman/sam3-mac.git@91c7b8b5be9643a1ec4fc52f84538145cc88b14c"

# 5. The rest of the pinned packages
pip install -r .bob/skills/carbon-placement-advisor/scripts/requirements.txt

# 6. Log in to HuggingFace. This prompts for your token on your own terminal.
hf auth login
```

### Check that it worked

```bash
cd .bob/skills/carbon-placement-advisor/scripts
../../../../.venv/bin/python check_env.py
```

You want to see `READY: all required checks passed.` Any `FAIL` line says what is missing. The first real review downloads the weights (about 5 GB), so it is slower once.

## Use it

Ask Bob in Agent mode, for example:

- "Review the placement in `designs/create-work-order.png`. Frame width 1312, exported at 1x."
- "Is this layout correct?" (attach a screenshot)
- "Where should these components go?" (give a Figma frame link)

Or run it yourself:

```bash
cd .bob/skills/carbon-placement-advisor/scripts
../../../../.venv/bin/python run_review.py \
  --image ../../../../designs/create-work-order.png \
  --output-dir ../../../../placement-reviews/create-work-order \
  --frame-width 1312
```

You get four files in the output folder:

| File | What it holds |
|---|---|
| `detections.json` | Raw shapes SAM 3 found, with scores |
| `components.json` | Shapes turned into Carbon components, with a confidence and the reason for each type |
| `findings.json` | The numbered placement issues: defect type, severity, which components, measured evidence, suggested fix |
| `annotated.png` | Your image with component boxes and numbered issue markers |

## How to read a result

- **`c1`, `c2`, ...** are detected components. They restart for every image.
- **`ISSUE-01`, `ISSUE-02`, ...** are the problems found in one review. The number is the marker on `annotated.png`.
- **`DEF-GRID-04`** and similar are defect types, defined in [`references/defect-taxonomy.md`](references/defect-taxonomy.md). Many issues can share one type.
- A **heuristic** rule is a guess from our own examples, not from Carbon. A designer should confirm it.

## What it cannot do yet

- A field with no chevron is reported as a TextInput, even if the design meant a Dropdown.
- It was tuned on five screens only, so accuracy on other pages is unproven. A set of held-out screens exists to measure this honestly.
- It measures placement. It does not judge colour, text, or whether the right component was chosen.
- Some rules were written for Work Order and Asset Catalog pages.

## Folder map

```
carbon-placement-advisor/
  SKILL.md                  What Bob reads: when to use the skill and the exact steps
  README.md                 This file
  scripts/
    check_env.py            Checks the setup (never reads your token)
    run_review.py           One command: detect > normalize > analyze > annotate
    detect_components.py    Runs SAM 3 on the image
    normalize_detections.py Turns shapes into Carbon-typed components
    analyze_layout.py       Measures and applies the placement rules
    annotate_image.py       Draws boxes and numbered markers
    prompt_vocab.json       Which SAM 3 phrases to use, and size limits per component
    requirements.txt        Pinned versions
    common.py               Shared helpers
  references/               Rules, defect list, prompt notes, report template
  evals/evals.json          Test questions for measuring the finished skill
```

The test images and answer keys live outside the skill, in `placement-corpus/` (calibration images used for tuning, and a held-out set kept as the final exam).

## Security notes

- The skill starts no server and opens no network port. The only network use is the HTTPS download of the SAM 3 weights from HuggingFace.
- Your token is stored by `hf auth login` and read by the HuggingFace library. The scripts never read, print or save it. Do not paste it into Bob.
- Your designs stay on your machine. `placement-reviews/` and `placement-corpus/outputs/` are git-ignored because they may hold unreleased designs.
- Dependencies are pinned. Run a vulnerability scan (for example `pip-audit`) and check licences and maintenance before upgrading or releasing. This has not yet been done for this release.
- SAM 3 loads its weights with `weights_only=True`, which refuses code embedded in the checkpoint.

## For maintainers

- `placement-corpus/calibration/` images are for tuning. `placement-corpus/held-out/` images are the final exam: do not run, tune against, or view them until the final evaluation.
- Answer keys are `labels.md` files next to the images. They are used only to measure accuracy, never at review time.
- `evals/evals.json` entries 1 to 5 use calibration images. Entries 6 to 9 use held-out images and still need their defect expectations (see `placement-corpus/held-out/labels.md`).
