# Carbon Placement Defect Taxonomy

This taxonomy categorizes layout and placement defects in UI screenshots and Figma designs against the Carbon Design System. Each defect specifies its unique ID, severity, detection mechanism, and recommended Carbon remediation.

---

## Severity Definitions

- **Blocker**: Critical layout breakdown (e.g. out-of-zone controls, unreadable hierarchy, broken grid collision).
- **Major**: Clear standard violation (e.g. off-token spacing, inverted action hierarchy, misaligned form stack).
- **Minor**: Subtle visual imperfection (e.g. $\pm 2\text{ px}$ spacing jitter, non-standard card height baseline).

---

## Defect Catalog

### 1. Grid & Alignment Defects (`DEF-GRID-*`)

| Defect ID | Defect Name | Severity | Detection Mode | Carbon Rule & Fix |
| :--- | :--- | :--- | :--- | :--- |
| **`DEF-GRID-01`** | **Off-Grid Column Alignment** | Major | Geometric | Component bounding box does not start or end on a 16/8/4 column boundary or gutter. <br>**Fix:** Snap $x_1$ and $x_2$ to nearest column grid line. |
| **`DEF-GRID-04`** | **Mismatched Sibling Widths** | Major | Geometric | Siblings that should share a width or column span differ (cards in one row, a text input beside a dropdown). Added because the analyzer reports it. <br>**Fix:** Give siblings the same column span. |
| **`DEF-GRID-02`** | **Non-Standard Column Span** | Minor | Geometric | Component width does not conform to integer column span calculation (e.g. partial column overhang). <br>**Fix:** Adjust width to snap to full column span (e.g., `lg=4`, `lg=8`, `lg=16`). |
| **`DEF-GRID-03`** | **Missing Page Margin** | Major | Geometric | Content touches the canvas/viewport boundary with $< 16\text{ px}$ outer margin. <br>**Fix:** Apply $16\text{ px}$ outer grid margin. |

---

### 2. Spacing Scale Defects (`DEF-SPACE-*`)

| Defect ID | Defect Name | Severity | Detection Mode | Carbon Rule & Fix |
| :--- | :--- | :--- | :--- | :--- |
| **`DEF-SPACE-01`** | **Non-Token Spacing Gap** | Major | Geometric | The measured gap between adjacent elements is not in the `$spacing-*` scale (e.g. 10px, 14px, 21px). <br>**Fix:** Round gap to nearest token: `$spacing-03` (8px), `$spacing-04` (12px), `$spacing-05` (16px), or `$spacing-06` (24px). |
| **`DEF-SPACE-02`** | **Inconsistent Sibling Gaps** | Major | Geometric (heuristic) | Unequal vertical/horizontal spacing between parallel elements in a list, stack, or grid row. The analyzer flags two same-row fields whose gap exceeds one grid column plus two gutters (114 px at 1312 px wide). <br>**Fix:** Apply uniform Carbon `Stack` gap (e.g., `gap={5}`) or place the field on the next grid column. |
| **`DEF-SPACE-03`** | **Over-Crowded / Insufficient Space** | Major | Geometric | Interactive targets placed $< 8\text{ px}$ apart without intentional grouping, causing touch target clash. <br>**Fix:** Increase separation to minimum `$spacing-03` (8px). |

---

### 3. Hierarchy & Alignment Defects (`DEF-ALIGN-*` / `DEF-HIER-*`)

| Defect ID | Defect Name | Severity | Detection Mode | Carbon Rule & Fix |
| :--- | :--- | :--- | :--- | :--- |
| **`DEF-ALIGN-01`** | **Staggered Form Stack Alignment** | Major | Geometric | Labels, text inputs, and dropdowns in the same form column have differing $x_1$ left coordinates. <br>**Fix:** Align all left edges to $x_1$. |
| **`DEF-ALIGN-02`** | **Button Group Not Aligned To Form Edge** | n/a | Retired | No longer reported. The rule assumed button groups end on the form's right edge, but a good page (good-02) left-aligns them. The id is kept so old reports still resolve. |
| **`DEF-ALIGN-03`** | **Misaligned Form Row Baseline** | Major | Geometric | Controls in one logical row start at different y positions. Added because the analyzer reports it. <br>**Fix:** Align the top edges. |
| **`DEF-PROX-01`** | **Detached Label / Field Proximity** | Major | Geometric + Class | Vertical distance between label text and input container exceeds `$spacing-04` ($> 12\text{ px}$). <br>**Fix:** Reduce gap to `$spacing-02` (4px) or `$spacing-03` (8px). |
| **`DEF-PROX-02`** | **Detached Action Button** | Major | Geometric (heuristic) | An action button sits at the far edge of the page, away from the controls it acts on. Added because the analyzer reports it. <br>**Fix:** Move it next to its controls, `$spacing-05` (16px) away. |
| **`DEF-HIER-01`** | **Inverted Button Hierarchy** | Major | Classification | Primary action button is placed to the left of the Secondary/Cancel button in a modal or form footer. <br>**Fix:** Place Secondary on the left, Primary on the far right. |
| **`DEF-HIER-02`** | **Duplicate Primary Actions** | Blocker | Classification | More than one Primary (high-emphasis) button present within a single content view. <br>**Fix:** Demote secondary tasks to `Secondary`, `Tertiary`, or `Ghost` buttons. |

---

### 4. Layout Zones & Component Pattern Defects (`DEF-ZONE-*`)

| Defect ID | Defect Name | Severity | Detection Mode | Carbon Rule & Fix |
| :--- | :--- | :--- | :--- | :--- |
| **`DEF-ZONE-01`** | **Pagination Above Table** | Blocker | Classification | `Pagination` component placed at the top or inside table content instead of bottom edge. <br>**Fix:** Move `Pagination` to the bottom of `DataTable`. |
| **`DEF-ZONE-02`** | **Toolbar Action Misplacement** | Major | Classification | Search/Filter actions placed below table data rows instead of inside the top Table Toolbar. <br>**Fix:** Move search and filter inputs into `TableToolbar`. |
| **`DEF-ZONE-03`** | **Shell Header Displaced** | Blocker | Classification | Global navigation / header bar placed inside page body or below hero container. <br>**Fix:** Anchor `Header` to top $y_1=0$, height 48px. |
| **`DEF-ZONE-04`** | **SideNav / Body Overlap** | Blocker | Geometric | Main page content overlaps the 256px wide left navigation rail. <br>**Fix:** Shift content container right to start at $x_1 = 256\text{ px}$ or use `<Content>` shell margin. |
