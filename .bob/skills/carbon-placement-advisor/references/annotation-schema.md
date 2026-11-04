# Annotation & Layout Review JSON Schema

This document specifies the JSON contract used for:
1. **Corpus Ground Truth:** Paired good vs. broken design annotations.
2. **Detection & Normalization Output:** Structured component detections from SAM 3.
3. **Layout Review Output:** Geometric findings, defect categories, and Carbon fix suggestions.

---

## 1. Corpus Sample Annotation Schema (`sample.json`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CarbonPlacementSample",
  "type": "object",
  "required": [
    "sample_id",
    "pair_id",
    "role",
    "frame_metadata",
    "components",
    "defects"
  ],
  "properties": {
    "sample_id": {
      "type": "string",
      "description": "Unique identifier, e.g., 'dashboard-01-good' or 'dashboard-01-bad-grid'"
    },
    "pair_id": {
      "type": "string",
      "description": "Shared identifier linking the good design with its broken variants"
    },
    "role": {
      "type": "string",
      "enum": ["good", "broken"]
    },
    "pattern_type": {
      "type": "string",
      "enum": ["dashboard", "data_table", "form", "settings", "modal", "detail_tabs"]
    },
    "frame_metadata": {
      "type": "object",
      "required": ["width", "height", "scale", "breakpoint"],
      "properties": {
        "width": { "type": "number", "description": "Frame width in design px, e.g. 1584" },
        "height": { "type": "number", "description": "Frame height in design px" },
        "scale": { "type": "number", "description": "Export scale factor, e.g. 1 or 2" },
        "breakpoint": { "type": "string", "enum": ["sm", "md", "lg", "xlg", "max"] }
      }
    },
    "components": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "type", "bbox"],
        "properties": {
          "id": { "type": "string", "example": "btn-submit-01" },
          "type": { "type": "string", "example": "Button" },
          "variant": { "type": "string", "example": "primary" },
          "bbox": {
            "type": "array",
            "items": { "type": "number" },
            "minItems": 4,
            "maxItems": 4,
            "description": "[x1, y1, x2, y2] in pixels"
          },
          "grid_span": {
            "type": "object",
            "properties": {
              "start_col": { "type": "integer" },
              "span_cols": { "type": "integer" }
            }
          }
        }
      }
    },
    "defects": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["defect_id", "category", "severity", "affected_components", "suggested_fix"],
        "properties": {
          "defect_id": { "type": "string", "example": "DEF-GRID-01" },
          "category": { "type": "string", "example": "Grid Misalignment" },
          "severity": { "type": "string", "enum": ["Blocker", "Major", "Minor"] },
          "affected_components": {
            "type": "array",
            "items": { "type": "string" }
          },
          "evidence": {
            "type": "string",
            "example": "Component left edge at x=412px misses column 5 boundary (429px)"
          },
          "suggested_fix": {
            "type": "object",
            "properties": {
              "target_span_lg": { "type": "integer" },
              "target_spacing_token": { "type": "string", "example": "$spacing-05" },
              "action": { "type": "string", "example": "Snap x1 to 429px and widen span to 4 cols" }
            }
          }
        }
      }
    }
  }
}
```
