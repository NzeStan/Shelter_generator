# Shelter Scaffold Report Generator

Generates an NLNG-branded shelter scaffold design report from STAAD.Pro command and output files. It is wired only for shelters: roof, seat ledgers and walking platform live loads, height-varying or uniform wind loading (WLX/WLZ) with roof uplift (WLY), uplift resistance by concrete blocks, friction, connection and deflection checks, and optional tie reactions.

## Setup

```bash
pip install jinja2 playwright Pillow pypdf
playwright install chromium
```

If browser PDF generation is unavailable, open the generated HTML in Chrome or Edge and print to PDF.

## Workflow

1. Fill `inputs/project_info.txt` with project data.
2. Paste the STAAD.Pro `.std` content into `inputs/staad_command.txt`.
3. Paste the STAAD.Pro `.out` content into `inputs/staad_output.txt`. It must include `PRINT MEMBER FORCES` results (used for the connection stability check).
4. Drop logos into `logo/` as `nlng_logo.png` and `company_logo.png`, or set URLs in `logo/logo_url.txt`.
5. Drop screenshots into `images/` using the names in `images/README.txt`.
6. Run `python generate_report.py`.
7. Collect the generated HTML and PDF from `output/`.

Useful flags: `--skip-3d-render` (reuse the existing `images/3d_model`), `--skip-engineering-drawings`, `--drawing-format {standard,grid,none}`.

## Shelter Project Info Fields

| Field | Purpose |
|---|---|
| `SCAFFOLD_TYPE`, `SHELTER_USE` | Wording of the brief description, e.g. "a Security shelter scaffold". |
| `SHELTER_TIED` | Set `yes` only when reactions are transferred to a parent structure. Tie reactions are X/Z only (`SHOW_TIE_REACTIONS`, `TIE_DISPLAY`, optional `TIE_FORCE_FX/FZ`). |
| `ROOF_LIVE_LOAD_KN_M2` | Roof live load intensity (BS EN 1991-1-1 Cl. 6.3.4.1, typically 0.4 kN/m2). |
| `SEAT_LIVE_LOAD_KN_M` | Seat ledger UDL (typically 0.75 kN/m). Also used to recognise the seat members. |
| `PLATFORM_LIVE_LOAD_KN_M2` | Main walking platform live load (typically 1.5 kN/m2). |
| `UPLIFT_RESISTANCE_ENABLED`, `UPLIFT_TOTAL_WLY_KN`, `UPLIFT_DEAD_LOAD_KN` | Uplift check. Leave the totals blank to read WLY and DL from the STAAD output. |
| `UPLIFT_ANCHORAGE_POINTS`, `CONCRETE_BLOCK_*` | Inputs for the concrete-block counterweight count. |
| `MAX_VERT_*`, `MAX_HORIZ_*` | Optional deflection overrides (auto-extracted from the `.out` file otherwise). |
| `MAX_AXIAL_*`, `MAX_AXIAL_SLS_*` | Optional overrides for the connection stability check (ULS first, SLS fallback). |
| `CATEGORY_1_ASSURANCE_NOTE` | `yes` prints "Category 1 Engineered Scaffold", otherwise Category 2. |

Roof, seat and platform members are classified automatically from STAAD member elevations and UDLs - there is no manual member-list override. Wind pressure `qw = qp x Cf` is generated entirely from the EN 1991-1-4:2005 calculation (`WIND_CALC_HEIGHT_M` overrides the height used, otherwise the shelter height) - there is no pressure override.

## STAAD Values Parsed

| Value | Source | Method |
|---|---|---|
| Shelter height, length, width | `.std` | Maximum Y, X and Z joint coordinates |
| Live load totals (platform, roof, seat) | `.std` / `.out` | Sum of member UDL x length per category; together they reproduce the live load case SUMMATION FORCE-Y |
| Wind loads WLX / WLZ | `.std` | Member UDLs, presented as `qw x tributary width`. Height-varying pressure (qp(z) evaluated per lift) is detected automatically and shown with its reference heights |
| Wind totals and uplift | `.out` | SUMMATION FORCE results for the wind load cases |
| Uplift resistance | `.out` + `project_info.txt` | `max(WLY - DL, 0)`, split over anchorage points and concrete block weight |
| Frictional resistance | `.std` | KFX/KFZ spring stiffness |
| Utilization ratios | `.out` | STAAD code-check block |
| Connection stability | `.out` | Peak axial force in horizontal ledgers/transoms from the member forces table |
| Parent-structure reactions | `.out` | X/Z tie reactions, only when `SHELTER_TIED: yes` |

## Output Layout

Cover/project data, load summary, general notes, load combinations, shelter load cases, wind pressure and load calculation, uplift resistance, load diagrams, utilization ratio summary, connection stability, friction, deflection checks, conclusion and references, followed by the engineering drawings.
