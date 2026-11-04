# Placement review report template

Use these headings in this order. Delete a section only if it has nothing to say, except Limitations, which is always present.

```markdown
# Placement review: <page name or file name>

**Assumed:** frame width <N> px, export scale <1|2>, breakpoint <xlg|lg|...>. Source: <user said / read from Figma / assumed>.
**Result:** <N> issues (<n> major, <n> minor, <n> blocker). Annotated image: <path to annotated.png>

## Summary
Two or three sentences. Say whether the layout is largely correct, and name the most serious problem.

## Issues
For each issue, in the order of the numbers on the annotated image:

### <number>. <category> (<defect_id>, <severity>)
- **Where:** <component ids and types, with box [x1, y1, x2, y2] in design px>
- **Evidence:** <the measured values from findings.json, copied exactly>
- **Suggested move:** <concrete target: x or y in px, column span (lg=N), or spacing token such as $spacing-05 (16px)>
- **Confidence:** <high | medium | low>, because <type confidence, or "heuristic rule, designer should confirm">

## What looks correct
List the components and relationships that were checked and passed. Do not invent items.

## Component inventory
| Id | Type | Confidence | Box (design px) | Notes |
|---|---|---|---|---|

## Limitations
- Types inferred from shapes: <list low-confidence ones>
- Not detected: <regions or elements the scripts could not find>
- Rules used that are heuristic: <list>
- Warnings from the run: <copy each warning>
- Assumptions: <scale, breakpoint, any intended layout you do not know>

## Next step
One question: which issue to explain or re-check first.
```

## Writing rules

- Use measured numbers from `findings.json`. Do not round them differently.
- One problem per issue. Do not merge two problems into one entry.
- Use Carbon vocabulary: column span (`lg=5`), spacing tokens (`$spacing-05`), Tile, Tag, Dropdown.
- Hedge when the intended layout is unknown. Do not hedge measured facts.
- Do not report an issue the scripts did not produce unless it is labelled **judgment**.
