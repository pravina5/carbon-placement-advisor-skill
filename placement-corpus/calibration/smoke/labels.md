# Answer key: calibration/smoke

Used to measure the pipeline (found / missed / false alarm). Not read by Bob at review time.
All files: 1312 x 738 px, export scale 1, frame width 1312 design px (assumed from the PNG size; confirm in Figma).
Coordinates are design px, [x1, y1, x2, y2]. 

## good-01.png
page: asset-catalog
paired_with: bad-01.png
defects: none
status: draft

## bad-01.png
page: asset-catalog
paired_with: good-01.png
status: draft
defects:
  1. Apply button detached from the filter row
     good: [823, 96, 884, 136]   bad: [1152, 44, 1211, 84]
     fix: return it to the filter row, 16 px ($spacing-05) after the "Show decommissioned" checkbox
  2. Third card (Conveyor 4) is wider than its siblings
     good: 776..1136 (360 wide)   bad: 776..1286 (510 wide)
     fix: all three cards share one width (360 px)

## good-03.png
page: create-work-order
paired_with: bad-05.png
defects: none
status: draft

## bad-05.png
page: create-work-order
paired_with: good-03.png
status: draft
defects:
  1. "Estimated hours" field left its row and the middle column
     good: row 2, column 2, starts x=328, y~=196
     bad: starts x=231, y~=270 (underline at [233, 323, 519, 326])
     fix: return to row 2, column 2 (x=328)
  2. "Description" field shifted right and overhangs the form
     good: [24, 464, 919, 468] underline, left edge x=24, right edge x=920
     bad: underline [375, 534, 1271, 538]
     fix: left edge x=24, right edge x=920

## bad-03.png
page: inspection-checklist
paired_with: none (no good twin in the set)
status: NEEDS TEAMMATE. Bob cannot know the intended layout without a good version.
defects:
  1. Button group (Save draft, Submit inspection) ends at x=1074, beyond the tab strip edge x=1034
  2. Inspector notes area is narrow (x=24..277) compared with the 1010 px tab strip

