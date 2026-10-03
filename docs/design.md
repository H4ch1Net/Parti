# Design

Art direction: **Construction Set**. The app is a drawing sheet on a desk. It borrows from architectural drawing sets (sheet frames, zone markers, grid bubbles, title blocks, scale bars, crop marks, redline) and from Swiss typography (one family, a strict grid, rules instead of boxes).

Tokens live in `frontend/src/styles/tokens.css`. Plan styles are in `plan.css`, and the interface is in `app.css`.

## Colour

The palette comes from Le Corbusier's Polychromie Architecturale. Exports use the light values on white paper (`backend/app/drawing/style.py`).

| Token | Vellum (light) | Cyanotype (dark) | Use |
|---|---|---|---|
| `--desk` | `#ece8dd` | `#081c3a` | Page behind the sheet |
| `--sheet` | `#fbf9f3` | `#0d2a52` | Panels |
| `--canvas` | `#fcfbf7` | `#0e2d58` | Drawing area |
| `--ink` | `#14181c` | `#eef3fa` | Text, walls, frames |
| `--ink-2` / `--ink-3` | `#4b5459` / `#5f696d` | `#b6c6dc` / `#829ec2` | Secondary text, labels |
| `--accent` | `#b3401b` orange vif | `#f2a65a` ochre | Redline only |
| `--zone-public` | `#f6e4cd` | `#213f66` | Living, kitchen, entry |
| `--zone-private` | `#dfe7d7` | `#163b5c` | Bedrooms, baths |
| `--zone-service` | `#d8e2e4` | `#1a3a67` | Laundry, garage, storage |
| `--zone-circulation` | `#ebe9e2` | `#12335f` | Halls, stairs |

Text pairs meet WCAG AA on their surfaces. Zones also carry a hatch on the 0.3 m planning grid (public dots, private 45° lines, service cross, circulation plain), so colour is never the only cue. The hatch patterns are defined once in `components/PlanPatterns.tsx`.

The accent marks only the selected room, the current variant, the active tab and the weakest score category. Errors use `--err` and a diamond icon. Warnings use `--warn` and a triangle.

## Type

Archivo Variable (weight 100 to 900, width 62 to 125%) is the only typeface. The same family is bundled for the PDF and PNG writers (`backend/app/drawing/fonts`, SIL OFL).

| Role | Setting |
|---|---|
| Wordmark | 800, width 125% |
| Section titles | 750, width 86%, capitals, 0.12em tracking |
| Labels | 650, width 86%, capitals, 0.09em tracking, 10.5px |
| Body | 400, 14px / 1.45 |
| Score numeral | 280, width 82%, 56px |
| Figures | tabular |

## Shape

- Square corners everywhere. Only grid bubbles and the spinner are round.
- Columns and cells are divided by 1px rules. Frames are 1.5px ink.
- Hard offset shadows (`3px 3px 0`) only on sheets that float: the room inspector and the dialog.
- No gradients, glass or glow. The repeating gradients in the CSS draw ticks, hatches and dot grids.

## Components

- **Section head**: a numbered bubble, a title, and a rule to the edge. Brief 1, Plan 2, Variants 3, Sheet 4.
- **Title block**: drawing name, variant bubble, score, area, footprint and checks, in ruled cells.
- **Scale meter**: scores are drawn as a scale bar with alternating ten-point blocks.
- **Layer toggles**: a visibility box beside each layer name.
- **Redline overlay**: selection is an accent outline with crop-mark brackets, drawn above the walls by `PlanCanvas`. Hover is dashed ink. Flagged rooms are dashed in the error colour.
- **Axonometric**: `components/Axo.tsx` draws a cut-away model for the empty, loading and error states.
- **Icons**: `components/Icon.tsx`, on a 24-unit grid with a 1.5 stroke, square caps and mitred joins.

## Motion

- New drawings are plotted in about 0.6 s: zones fade, then walls and furniture wipe in, then labels.
- While a plan is generating, the axonometric walls drop into place one at a time.
- Elsewhere, motion is limited to quick colour changes and the inspector settling in.
- All animation stops under `prefers-reduced-motion`.

## Responsive and accessibility

- **Desktop**: three columns, with the masthead aligned to the same grid.
- **Below 1100px**: two columns, and the title block moves under the plan.
- **Below 760px**: one column, the frame is dropped, and the inspector docks to the bottom of the canvas.
- **Accessibility**: focus is a 2px accent outline. Toggles, segmented controls and selected variants have forced-colours fallbacks.

## Exports and brand

- **Exports**: the PDF is an A3 sheet with a trim line, a frame and lettered/numbered zones. PDF, SVG and PNG exports share one title block (`backend/app/drawing/titleblock.py`): mark, drawing, and a "Not for construction" status.
- **Brand images**: the banner, social image and touch icon are rendered from the tokens and a real plan by `frontend/scripts/brand.mjs` (`make brand`, with the API running). The favicon is the mark: a split plan with one room in redline.
