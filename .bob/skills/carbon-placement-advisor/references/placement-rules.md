# Carbon Placement & Layout Rules

This reference defines the authoritative geometric, spatial, and hierarchical rules of the **Carbon Design System (v11)**. These rules serve as the standard against which UI screenshots and Figma frames are analyzed and critiqued.

---

## 1. The Carbon 2x Grid System

The IBM Design 2x Grid is the structural framework for all page layouts, alignment, and responsiveness.

### 1.1 Breakpoints & Columns

| Breakpoint Name | Screen Width (px) | Columns | Gutter Width | Margin Width |
| :--- | :--- | :--- | :--- | :--- |
| **`sm`** (Small) | 320 – 671 px | **4** | 16 px | 16 px |
| **`md`** (Medium) | 672 – 1055 px | **8** | 16 px | 16 px |
| **`lg`** (Large) | 1056 – 1311 px | **16** | 32 px (wide) / 16 px (narrow) | 16 px |
| **`xlg`** (Extra Large) | 1312 – 1583 px | **16** | 32 px (wide) / 16 px (narrow) | 16 px |
| **`max`** (Maximum) | 1584 px + | **16** | 32 px (wide) / 16 px (narrow) | 16 px / 24 px |

### 1.2 Grid Mathematical Span Formula

When mapping detected bounding box widths ($W_{px}$) in pixels to Carbon grid column spans ($S_{cols}$):

$$S_{cols} = \min\left(\text{TotalColumns}, \max\left(1, \left\lceil \frac{W_{px} + \text{Gutter}}{\text{ColumnWidth} + \text{Gutter}} \right\rceil\right)\right)$$

Where at `lg` / `max` (1584px width, 16 columns, 32px gutters, 16px margins):
- Total Content Width = $1584 - (2 \times 16) = 1552\text{ px}$
- Total Gutters Width = $15 \times 32 = 480\text{ px}$
- Total Columns Width = $1552 - 480 = 1072\text{ px}$
- **Single Column Width ($W_{col}$)** = $1072 / 16 = 67\text{ px}$
- **Column Pitch ($W_{col} + \text{Gutter}$)** = $67 + 32 = 99\text{ px}$

---

## 2. Spacing Scale Tokens ($spacing-01 to $spacing-13)

All layout margins, paddings, and component gaps **must** snap to the official Carbon spacing scale:

| Token Name | Rem Value | Pixel Value (8px Mini-Unit) | Primary Usage |
| :--- | :--- | :--- | :--- |
| **`$spacing-01`** | `0.125rem` | **2 px** | Micro adjustments, tight borders |
| **`$spacing-02`** | `0.25rem` | **4 px** | Inline icon-to-text gap, badge padding |
| **`$spacing-03`** | `0.5rem` | **8 px** | Compact intra-component padding, label-to-input gap |
| **`$spacing-04`** | `0.75rem` | **12 px** | Form helper text spacing, small stack gaps |
| **`$spacing-05`** | `1.0rem` | **16 px** | Standard component padding, card padding, default form field gap |
| **`$spacing-06`** | `1.5rem` | **24 px** | Medium section gap, tile internal spacing |
| **`$spacing-07`** | `2.0rem` | **32 px** | Standard content block separation, wide grid gutter |
| **`$spacing-08`** | `2.5rem` | **40 px** | Page sub-section separation |
| **`$spacing-09`** | `3.0rem` | **48 px** | Major section separation |
| **`$spacing-10`** | `4.0rem` | **64 px** | Page hero banner padding, major layout grouping |
| **`$spacing-11`** | `5.0rem` | **80 px** | Editorial / landing page block separation |
| **`$spacing-12`** | `6.0rem` | **96 px** | Large display white space |
| **`$spacing-13`** | `10.0rem` | **160 px** | Maximum whitespace separation |

### Rule: Tolerance Threshold
- Off-scale values within $\pm 1\text{ px}$ are considered rounding artifacts.
- Gaps differing by $\ge 2\text{ px}$ from the nearest token (e.g. 10px, 14px, 20px, 28px) constitute a **Spacing Violation**.

---

## 3. Structural Alignment & Proximity Rules

1. **Left-Edge Alignment:** Sibling form items (labels, inputs, helper text) or stacked tiles in the same column group must share an identical left pixel boundary ($x_1$).
2. **Label-Input Proximity:** A field label must be positioned within `$spacing-02` (4px) to `$spacing-03` (8px) directly above its associated input container. Gaps $> 16\text{ px}$ break the visual association.
3. **Form Field Stacking:** Consecutive form fields in a single column stack should maintain a consistent vertical gap of `$spacing-05` (16px) or `$spacing-06` (24px).
4. **Card / Tile Uniformity:** Adjacent cards in a multi-column row must share identical top coordinates ($y_1$) and matching height or aligned bottom baselines.

---

## 4. Visual Hierarchy & Action Placement

1. **Button Ordering (Left-to-Right):**
   - For form submit/cancel flows: Secondary/Ghost button (e.g. "Cancel") appears to the left; **Primary button ("Submit", "Save") appears to the right**.
   - Primary action must only appear **once** per screen/dialog to maintain high visual contrast.
2. **Data Table Actions & Pagination:**
   - Table Search, Filter, and Batch actions belong in the **Table Toolbar** (above table header row).
   - **Pagination** belongs exclusively at the **bottom edge** of the Data Table. Placing pagination above the table is a pattern violation.
3. **Page Scaffolding & Zones:**
   - **Header / Shell:** Fixed top banner (height 48px).
   - **Side Navigation:** Left rail occupying 256px wide / 4 cols (`lg`).
   - **Page Header / Breadcrumb:** Directly below Header, preceding page content.
   - **Main Content:** Occupies remaining fluid column grid with minimum 16px outer margin.
