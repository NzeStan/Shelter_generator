# Shelter Scaffold Report Generator

Generates an NLNG-branded shelter scaffold design report from STAAD.Pro command and output files. This `SHELTER` copy is derived from the scaffold report generator but is wired for shelter roofs, seat ledgers, wind ledger loads, WLY uplift, uplift-resistance counterweight, friction, and optional tie reactions.

## Setup

```bash
pip install jinja2 playwright Pillow pypdf
playwright install chromium
```

If browser PDF generation is unavailable, open the generated HTML in Chrome or Edge and print to PDF.

## Workflow

1. Fill `inputs/project_info.txt` with project data and shelter inputs.
2. Paste the STAAD.Pro `.std` content into `inputs/staad_command.txt`.
3. Paste the STAAD.Pro `.out` content into `inputs/staad_output.txt`.
4. Drop logos into `logo/` as `nlng_logo.png` and `company_logo.png`, or set URLs in `logo/logo_url.txt`.
5. Drop screenshots into `images/` using the names in `images/README.txt`.
6. Run `python generate_report.py`.
7. Collect the generated HTML and PDF from `output/`.

## Shelter Project Info Fields

| Field | Purpose |
|---|---|
| `SHELTER_TYPE` | `gable` for symmetric/gable shelters, `sloped` when windward/leeward ledger loads differ. |
| `SHELTER_TIED` | Set `yes` only when reactions are transferred to a parent structure. Tie reactions are X/Z only. |
| `ROOF_LIVE_LOAD_KN_M2` | Roof live load intensity, default template value `0.4 kN/m2` per BS EN 1991-1-1 Clause 6.3.4.1. |
| `SEAT_LIVE_LOAD_KN_M` | Seat ledger UDL, default template value `0.75 kN/m`. |
| `PLATFORM_LIVE_LOAD_KN_M2` | Main walking platform live load, default template value `1.5 kN/m2`. |
| `UPLIFT_TOTAL_WLY_KN`, `UPLIFT_DEAD_LOAD_KN` | Optional uplift overrides; leave blank to read WLY and DL totals from STAAD output. |
| `UPLIFT_ANCHORAGE_POINTS`, `CONCRETE_BLOCK_*` | Inputs for concrete-block counterweight count. |

Roof, seat, and platform members are classified automatically from STAAD member elevations and UDLs -
there is no manual member-list override. Shelter wind pressure `qw = qp x Cf` is generated entirely from
the EN 1991-1-4:2005 calculation (using the shelter height as `z`) - there is no `project_info.txt` override.

## STAAD Values Parsed

| Value | Source | Method |
|---|---|---|
| Shelter height, length, width | `.std` | Maximum Y, X, and Z joint coordinates |
| Live load member UDLs | `.std` / `.out` | LL member UDLs and applied-load summary |
| Roof live load | `.std` + `project_info.txt` | Top shelter member groups; `ROOF_LIVE_LOAD_KN_M2 x tributary width` |
| Seat live load | `.std` + `project_info.txt` | Seat ledger member groups; `SEAT_LIVE_LOAD_KN_M` |
| Main platform live load | `.std` + `project_info.txt` | Platform member groups; `PLATFORM_LIVE_LOAD_KN_M2 x tributary width` |
| Wind ledger loads | `.std` (wind calc auto) | `qw x tributary width`, where `qw = qp x Cf` and `qp` is calculated for `z` = shelter height |
| Wind uplift | `.std` / `.out` | WLY load case total from SUMMATION FORCE-Y |
| Uplift resistance | `.out` + `project_info.txt` | `max(WLY - DL, 0)`, split over anchorage points and concrete block weight |
| Frictional resistance | `.std` | KFX/KFZ spring stiffness, always reported for shelter |
| Parent-structure reactions | `.out` | X/Z tie reactions only when `SHELTER_TIED: yes` |

## Output Layout

The report includes cover/project data, general notes, shelter load cases, wind pressure and ledger-load calculation, uplift-resistance counterweight, load combinations, utilization summary, connection/friction checks, deflection checks, conclusion, references, and optional drawings.
