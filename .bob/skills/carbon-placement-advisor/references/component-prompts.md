# SAM 3 prompts and how they become Carbon components

SAM 3 returns **shapes for a phrase**, not Carbon component types. It is a general vision model, not trained on UI. So each prompt finds shapes, and `normalize_detections.py` decides the Carbon type from geometry and from helper evidence.

The source of truth is [`scripts/prompt_vocab.json`](../scripts/prompt_vocab.json): each prompt and the Carbon type(s) it can produce, plus size limits per type. All prompts in that file run by default.

Results below come from the 5 calibration screens (1312 x 738, 1x) at threshold 0.25. Held-out screens were not used.

## 1. Which prompt finds which Carbon component

| Carbon component | Found by | How |
| :--- | :--- | :--- |
| Tile (card) | `rectangle`, `white rectangle` | Kept only if at least 160 x 96 px |
| Button, Tag | `button` | Tag if the height is 18 to 24 px, otherwise Button |
| Button (recovered) | `rectangle` | SAM 3 often boxes a filled button under `rectangle`, not `button`. A `rectangle` hit that is too small for a Tile is kept as a Button only if it is button-sized (30 to 80 px tall) and its border is one solid dark or saturated colour. White fields, white tabs and light table headers fail this test. Ghost and secondary buttons are not recovered. |
| Dropdown | `dropdown menu`, `text input field` + `down arrow` | A chevron in the right 30 percent of a field makes it a Dropdown |
| TextInput | `text input field`, `horizontal line` | Means "a field with no chevron or stepper" |
| NumberInput | `horizontal line` + `plus sign` + `minus sign` | Both signs in the right 30 percent of a field |
| TextArea | `horizontal line` | An underline with more than 140 px of empty space above it |
| Tab (selected, unselected) | `grey tab` + `horizontal line` | A grey strip is the unselected tabs; a blue line at its left edge is the selected tab |
| Checkbox | `checkbox` | |
| Icon | `icon` | 12 to 48 px |

## 2. Helper prompts

Types starting with `_` are evidence only and are never output as components.

| Prompt | Helper type | Used to |
| :--- | :--- | :--- |
| `horizontal line` | `_Line` | Find Carbon field underlines (Carbon fields are underlines, not boxes) and the selected-tab indicator |
| `grey tab` | `_TabStrip` | Find the strip of unselected tabs (at least 300 x 32 px) |
| `down arrow` | `_Chevron` | Mark a field as Dropdown |
| `plus sign`, `minus sign` | `_Plus`, `_Minus` | Mark a field as NumberInput (both needed) |

## 3. Phrases that returned no shapes of their own

SAM 3 returned nothing useful for these exact phrases, so the components are found through the prompts in section 1 instead. They stay in `prompt_vocab.json` and run with the rest:

`card`, `tag`, `link`, `heading text`, `section`, `panel`, `tab bar`. Also tried and not kept: `tile`, `container`, `frame`, `badge`, `pill`, `chip`, `selected tab` (it finds buttons).

## 4. Other phrases in the vocabulary

`toggle switch`, `radio button`, `data table`, `header bar`, `side navigation`, `modal dialog`, `search bar`, `pagination controls`, `breadcrumb`, `notification banner`. The calibration screens do not contain these components, so there is no evidence about them yet. Use `--prompts` to try one on a page that has it.

## 5. How types are decided (heuristics, tuned on 3 to 5 pages)

- **Geometry gate:** a hit that fits none of its candidate types is dropped, not guessed.
- **TextArea:** the 140 px of empty space is a guess tuned on 3 pages.
- **TextInput:** only means "no chevron or stepper found". A Dropdown drawn without a chevron is reported as TextInput.
- **Unselected tabs:** edges are estimated midway between counted labels.
- **Field top edge:** fields known only from an underline use a 40 px height estimate, marked `top_edge_estimated`.
- A line exactly one field height above another field's underline is that field's top border, not a new field.

## 6. Known weaknesses

- A Dropdown without a chevron is typed TextInput (seen on the Title field of `bad-05`).
- TextArea relies on the 140 px rule.
- Accuracy numbers were measured on the images used for tuning, so they are optimistic.
- Primary and secondary buttons are not told apart. That would need fill colour.

## 7. Adding a prompt

1. Run `detect_components.py --prompts "<phrase>"` on a calibration image.
2. Open the result and check the boxes against the picture.
3. Add it to `prompt_vocab.json` with `types`, and a `geometry` entry if it is a new type.
4. Re-run all calibration images and confirm the good pages still report 0 issues.
5. Record it in this file.
