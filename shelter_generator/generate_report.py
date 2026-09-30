

def _resolve_css_vars(html):
    """Inline CSS custom properties - xhtml2pdf does not support var() syntax."""
    subs = {
        'var(--navy)':       '#0A2342',
        'var(--navy-mid)':   '#1B4B82',
        'var(--navy-light)': '#2C5F8A',
        'var(--gold)':       '#C8951A',
        'var(--gold-light)': '#F0C040',
        'var(--bg-row)':     '#EBF2FA',
        'var(--bg-hdr)':     '#D0E4F5',
        'var(--border)':     '#94AFC8',
        'var(--text)':       '#1A1A2E',
        'var(--muted)':      '#4A5568',
        'var(--white)':      '#FFFFFF',
        'var(--pass-bg)':    '#D4EDDA',
        'var(--pass-fg)':    '#155724',
        'var(--fail-bg)':    '#F8D7DA',
        'var(--fail-fg)':    '#721C24',
    }
    for var, val in subs.items():
        html = html.replace(var, val)
    return html


def _try_system_browser(html_path, pdf_path):
    """Use Chrome or Edge already installed on this machine - no extra downloads needed."""
    import subprocess, os
    candidates = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        os.path.expandvars(r'%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe'),
        '/usr/bin/google-chrome',
        '/usr/bin/chromium-browser',
        '/usr/bin/chromium',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ]
    for exe in candidates:
        if exe and os.path.exists(exe):
            try:
                subprocess.run([
                    exe, '--headless', '--disable-gpu', '--no-sandbox',
                    '--disable-software-rasterizer',
                    f'--print-to-pdf={pdf_path}',
                    '--no-pdf-header-footer',
                    f'file:///{html_path.resolve().as_posix()}',
                ], capture_output=True, timeout=30)
                if pdf_path.exists():
                    label = 'Chrome' if 'chrome' in exe.lower() else 'Edge'
                    print(f"  PDF   ->  {pdf_path}  [via system {label}]")
                    return True
            except Exception:
                continue
    return False



"""
Shelter Scaffold Design Report Generator
Usage:  python generate_report.py
Output: output/<DOC_NO>_Report.html and .pdf when a PDF engine is available
"""
import argparse
import os
import re
import sys
import base64
import math
import subprocess
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from datetime import datetime

ROOT     = Path(__file__).parent
INPUTS   = ROOT / 'inputs'
LOGO_DIR = ROOT / 'logo'
IMG_DIR  = ROOT / 'images'
TMPL_DIR = ROOT / 'templates'
OUT_DIR  = ROOT / 'output'
PROJECT_ROOT = ROOT.parent
RENDERER_DIR = PROJECT_ROOT / '3D Renderer'
DRAWING_DIR  = PROJECT_ROOT / '2D_3D_GENERATOR'

sys.path.insert(0, str(ROOT))
from parsers.staad_parser import StaadParser
from parsers.wind_calc    import WindCalculator

# -- Project info --------------------------------------------------------------

DEFAULTS = {
    'DOCUMENT_NO':       'PMS-WA-ARCO-XXX',
    'SCAFFOLD_DRAWING_NO': '',
    'REVISION':          '0',
    'LOCATION':          'TRAIN X',
    'AREA':              'X',
    'SCAFFOLD_TYPE':     'Shelter Scaffold',
    'SHELTER_USE':       '',
    'SHELTER_TIED':      'no',
    'ROOF_LIVE_LOAD_KN_M2': '',
    'SEAT_LIVE_LOAD_KN_M': '',
    'PLATFORM_LIVE_LOAD_KN_M2': '',
    'OCCUPANT_MASSES_KG': '80,100',
    'UPLIFT_RESISTANCE_ENABLED': 'yes',
    'UPLIFT_TOTAL_WLY_KN': '',
    'UPLIFT_DEAD_LOAD_KN': '',
    'UPLIFT_ANCHORAGE_POINTS': '',
    'CONCRETE_BLOCK_LENGTH_M': '',
    'CONCRETE_BLOCK_WIDTH_M': '',
    'CONCRETE_BLOCK_HEIGHT_M': '',
    'CONCRETE_UNIT_WEIGHT_KN_M3': '',
    'CATEGORY_1_ASSURANCE_NOTE': '',
    'RISK_LEVEL':        'Medium',       # High / Medium / Low
    'PERMIT_NO':         '',
    'ERMT_NO':           '',
    'DESIGNED_BY_ID':    '',
    'DESIGNED_BY_NAME':  '',
    'VERIFIED_BY_ID':    '',
    'VERIFIED_BY_NAME':  '',
    'CHECKED_BY_ID':     '',
    'CHECKED_BY_NAME':   '',
    'REVIEWED_BY_ID':    '',
    'REVIEWED_BY_NAME':  '',
    'APPROVED_BY_ID':    '',
    'APPROVED_BY_NAME':  '',
    'WORK_ORDER':        '',
    'PURPOSE':           'maintenance activities',
    'STRUCTURE_ABOVE_GROUND_M': '',
    'WIND_CALC_HEIGHT_M': '',
    'DOC_LIFE':          '3 Years',
    'PREPARED_BY_NAME':  '',   # falls back to DESIGNED_BY_NAME if blank
    'AUTO_RENDER_3D_MODEL': 'yes',
    'AUTO_ENGINEERING_DRAWINGS': 'yes',
    'ENGINEERING_DRAWING_FORMAT': 'standard',
}

REPORT_OUTLINE = [
    ("load-summary", "Load Summary"),
    ("general-note", "General Note, Material Properties & Modelling Philosophy"),
    ("load-combs", "Load Combinations"),
    ("load-cases", "Load Cases"),
    ("wind-calc", "Wind Load Calculation"),
    ("uplift-resistance", "Uplift Resistance / Counterweight Calculation"),
    ("load-diagrams", "Load Diagrams"),
    ("uc-summary", "Utilization Ratio Summary"),
    ("connection-check", "Connection Stability Check"),
    ("deflection-check", "Deflection Check Results"),
    ("conclusion", "Conclusion, Recommendations & Installation Notes"),
    ("references-standards", "References & Standards"),
]

def parse_project_info(path):
    info = dict(DEFAULTS)
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if ':' in line and not line.startswith('#'):
                    k, _, v = line.partition(':')
                    info[k.strip()] = v.strip()
    except FileNotFoundError:
        print(f"  [WARN] {path} not found - using defaults")

    if not info['SCAFFOLD_DRAWING_NO']:
        info['SCAFFOLD_DRAWING_NO'] = info['DOCUMENT_NO']
    if not info['PREPARED_BY_NAME']:
        info['PREPARED_BY_NAME'] = info['DESIGNED_BY_NAME']
    return info


def _optional_float(value):
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_number(value):
    if value is None:
        return ''
    return f"{float(value):g}"


# -- Logo / image loading ------------------------------------------------------

def load_logo(name):
    """Return {'src': '...'} - URL takes priority over PNG."""
    url_file = LOGO_DIR / 'logo_url.txt'
    if url_file.exists():
        for line in url_file.read_text().splitlines():
            if line.strip().upper().startswith(f'{name.upper()}_URL:'):
                url = line.split(':', 1)[1].strip()
                if url:
                    return {'src': url}

    for ext in ('.png', '.jpg', '.jpeg'):
        png = LOGO_DIR / f'{name.lower()}_logo{ext}'
        if png.exists():
            b64  = base64.b64encode(png.read_bytes()).decode()
            mime = 'image/jpeg' if ext != '.png' else 'image/png'
            return {'src': f'data:{mime};base64,{b64}'}
    return None


def load_image(name):
    """Return base64 data URI or None (triggers placeholder in template)."""
    for ext in ('.png', '.jpg', '.jpeg'):
        p = IMG_DIR / f'{name}{ext}'
        if p.exists():
            b64  = base64.b64encode(p.read_bytes()).decode()
            mime = 'image/jpeg' if ext != '.png' else 'image/png'
            return f'data:{mime};base64,{b64}'
    return None


def find_image_file(name):
    for ext in ('.png', '.jpg', '.jpeg'):
        p = IMG_DIR / f'{name}{ext}'
        if p.exists():
            return p
    return None


def parse_args():
    ap = argparse.ArgumentParser(description="Generate a shelter scaffold design report.")
    ap.add_argument(
        "--drawing-format",
        choices=("standard", "grid", "none"),
        help="Engineering drawing format to generate and append. Overrides project_info.txt.",
    )
    ap.add_argument(
        "--skip-3d-render",
        action="store_true",
        help="Use the existing images/3d_model image instead of calling the 3D renderer.",
    )
    ap.add_argument(
        "--skip-engineering-drawings",
        action="store_true",
        help="Do not generate or append the four engineering drawing PDFs.",
    )
    return ap.parse_args()


def _bool_setting(value, default=True):
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "yes", "y", "true", "on"}


def _project_value(project, *keys):
    for key in keys:
        value = project.get(key, "")
        if str(value).strip():
            return str(value).strip()
    return ""


def _project_float(project, *keys, default=None):
    value = _extract_first_float(_project_value(project, *keys))
    return value if value is not None else default


def _project_int(project, *keys, default=0):
    value = _project_float(project, *keys, default=None)
    return int(round(value)) if value is not None else default


LOAD_CLASS_INTENSITIES = {
    "1": 0.75,
    "2": 1.50,
    "3": 2.00,
    "4": 3.00,
    "5": 4.50,
    "6": 6.00,
}


def _extract_first_float(value):
    m = re.search(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', str(value or ""))
    return float(m.group(0)) if m else None


def _format_load_value(value):
    if value is None:
        return ""
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _indefinite_article(text):
    clean = str(text or "").strip()
    return "an" if clean[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


def _fmt_width(value):
    return f"{float(value):.3f}"


def _load_class_for_intensity(intensity):
    """Return BS EN 12811-1 class string for the given intensity, or '' if unmatched."""
    for cls, cls_int in LOAD_CLASS_INTENSITIES.items():
        if abs(float(intensity or 0.0) - cls_int) < 0.026:
            return cls
    return ""


def _live_member_geometry(member_id, structural):
    members = structural.get("members", {})
    nodes = (structural.get("geometry", {}) or {}).get("nodes", {})
    member = members.get(member_id)
    if not member:
        return None

    p1 = nodes.get(member.get("j1"))
    p2 = nodes.get(member.get("j2"))
    if not p1 or not p2:
        return None

    dx = abs(p2[0] - p1[0])
    dz = abs(p2[2] - p1[2])
    if dx < 1e-3 and dz < 1e-3:
        # Purely vertical member (a standard lift segment) - no horizontal run at all,
        # so neither X nor Z is naturally "the" perpendicular coordinate. Tolerance is
        # 1mm, not exact-zero: STAAD node coordinates carry their own rounding noise
        # (e.g. 4.80001 vs 4.8), and comparing against an exact-zero threshold silently
        # misclassified a standard as a sloped/horizontal member instead, dropping it out
        # of its own grid and throwing off its neighbours' bay-width calculation. Report
        # both X and Z; _resolve_vertical_tributary_axis decides per load case which one
        # actually varies across sibling standards (e.g. a row of standards along one
        # wall face varies in X at a constant Z) and fills in a usable perp_coord.
        return {
            "axis": "VERTICAL",
            "y_mid": round((p1[1] + p2[1]) / 2.0, 3),
            "x": round((p1[0] + p2[0]) / 2.0, 3),
            "z": round((p1[2] + p2[2]) / 2.0, 3),
        }
    if dx >= dz:
        axis = "X"
        perp_idx = 2
    else:
        axis = "Z"
        perp_idx = 0

    return {
        "axis": axis,
        "y_mid": round((p1[1] + p2[1]) / 2.0, 3),
        "perp_coord": round((p1[perp_idx] + p2[perp_idx]) / 2.0, 3),
    }


def _resolve_vertical_tributary_axis(member_entries):
    """Vertical standards have no run direction to derive a perpendicular coordinate
    from. Per load case, check whether their sibling standards actually vary in X or in
    Z (e.g. a row of standards along one wall face varies in X at a fixed Z) and use
    whichever one varies as the tributary-spacing coordinate, same as a real horizontal
    member's perp_coord.

    That choice is made once per load case, but a wind case can load standards on more
    than one wall line (e.g. a front wall and a return wall), each with its own spacing.
    Comparing every standard's X position against every other regardless of which wall
    it's actually on mixes unrelated bay spacings together. So the *other* coordinate -
    the one that's supposed to be fixed for a given wall - is folded into the elevation
    key, keeping each wall's standards grouped only against their own real neighbours.
    """
    by_case = {}
    for entry in member_entries:
        geom = entry.get("geometry")
        if geom and geom.get("axis") == "VERTICAL":
            by_case.setdefault(entry["load_case"], []).append(geom)

    for geoms in by_case.values():
        xs = {g["x"] for g in geoms}
        zs = {g["z"] for g in geoms}
        use_x = len(xs) >= len(zs)
        for g in geoms:
            g["axis"] = "V"
            g["perp_coord"] = g["x"] if use_x else g["z"]
            # Rounded coarser than the 3dp node precision: this is only used to tell
            # "same wall" apart from "different wall", and a couple of standards on the
            # same wall line can carry a ~1cm node-position discrepancy (e.g. 0.30 vs
            # 0.31) that would otherwise split one wall into two spurious groups.
            g["y_mid"] = (g["y_mid"], round(g["z"] if use_x else g["x"], 1))


WIND_TIER_ELEVATION_GAP_M = 0.6
# Standards whose lift segment is cut short by a sloped roof land at a slightly
# different height member-to-member even though they're the same real design tier
# (observed spread up to ~0.4m on a single-pitch roof); genuinely different design
# tiers/lifts are spaced much further apart (~1m+ in every project seen so far). This
# gap sits between the two, so elevations within it cluster together as one tier while
# real tier boundaries still split.


def _assign_tributary_widths(member_entries, group_by_elevation=True):
    """Classify each member as Edge/Interior and size its tributary width from the spacing
    of neighbouring members. group_by_elevation=False ignores the member's Y level when
    grouping - needed for sloped/roof members that never share an exact elevation.

    When group_by_elevation=True, members are first bucketed by (load case, run axis,
    wall) and then clustered within each bucket by elevation gap (see
    WIND_TIER_ELEVATION_GAP_M) rather than requiring an exact height match: a vertical
    standard's topmost lift segment is cut off wherever a sloped roof happens to meet
    that particular standard, so its exact height can differ standard to standard even
    though they're all genuinely neighbours in plan and belong to the same real pressure
    tier. Clustering finds them without needing a hand-off to a second, coarser pass -
    and without letting a coincidental partial height match (two members that happen to
    share an exact height by chance) claim a smaller, wrong set of neighbours than the
    tier actually has.
    """
    def _run_pass(entries, key_fn):
        groups = {}
        for entry in entries:
            geom = entry.get("geometry")
            if not geom:
                continue
            groups.setdefault(key_fn(entry, geom), set()).add(geom["perp_coord"])

        for entry in entries:
            geom = entry.get("geometry")
            if not geom:
                continue

            coords = sorted(groups.get(key_fn(entry, geom), []))
            if len(coords) < 2 or geom["perp_coord"] not in coords:
                continue

            idx = coords.index(geom["perp_coord"])
            if idx == 0:
                bay = coords[1] - coords[0]
                tw = bay / 2.0
                entry["member_role"] = "Edge"
                entry["tributary_width_m"] = round(tw, 3)
                entry["tributary_width_display"] = f"{_fmt_width(bay)} / 2 = {_fmt_width(tw)}"
            elif idx == len(coords) - 1:
                bay = coords[-1] - coords[-2]
                tw = bay / 2.0
                entry["member_role"] = "Edge"
                entry["tributary_width_m"] = round(tw, 3)
                entry["tributary_width_display"] = f"{_fmt_width(bay)} / 2 = {_fmt_width(tw)}"
            else:
                left_half = (coords[idx] - coords[idx - 1]) / 2.0
                right_half = (coords[idx + 1] - coords[idx]) / 2.0
                tw = left_half + right_half
                entry["member_role"] = "Interior"
                entry["tributary_width_m"] = round(tw, 3)
                entry["tributary_width_display"] = (
                    f"({_fmt_width(left_half)} + {_fmt_width(right_half)}) = {_fmt_width(tw)}"
                )

    if group_by_elevation:
        buckets = {}
        for entry in member_entries:
            geom = entry.get("geometry")
            if not geom:
                continue
            y_mid = geom["y_mid"]
            height = y_mid[0] if isinstance(y_mid, tuple) else y_mid
            wall = y_mid[1] if isinstance(y_mid, tuple) else None
            buckets.setdefault((entry["load_case"], geom["axis"], wall), []).append((entry, height))

        for bucket in buckets.values():
            bucket.sort(key=lambda pair: pair[1])
            cluster_id = 0
            prev_height = None
            for entry, height in bucket:
                if prev_height is not None and height - prev_height > WIND_TIER_ELEVATION_GAP_M:
                    cluster_id += 1
                entry["_elevation_cluster"] = cluster_id
                prev_height = height

        _run_pass(member_entries, lambda entry, geom: (
            entry["load_case"], geom["axis"],
            geom["y_mid"][1] if isinstance(geom["y_mid"], tuple) else None,
            entry.get("_elevation_cluster"),
        ))
        for entry in member_entries:
            entry.pop("_elevation_cluster", None)
    else:
        _run_pass(member_entries, lambda entry, geom: (entry["load_case"], geom["axis"]))


def _member_group_summary(member_ids, structural):
    members = structural.get("members", {})
    nodes = (structural.get("geometry", {}) or {}).get("nodes", {})
    ids = sorted(set(int(mid) for mid in member_ids or []))
    coords = []
    lengths = []
    axes = {"X": 0, "Y": 0, "Z": 0, "DIAG": 0}

    for mid in ids:
        member = members.get(mid)
        if not member:
            continue
        p1 = nodes.get(member.get("j1"))
        p2 = nodes.get(member.get("j2"))
        if not p1 or not p2:
            continue
        coords.extend([p1, p2])
        lengths.append(member.get("length_mm", 0.0) / 1000.0)
        dx = abs(p2[0] - p1[0])
        dy = abs(p2[1] - p1[1])
        dz = abs(p2[2] - p1[2])
        if dy > dx and dy > dz:
            axes["Y"] += 1
        elif dx > dz and dx > dy:
            axes["X"] += 1
        elif dz > dx and dz > dy:
            axes["Z"] += 1
        else:
            axes["DIAG"] += 1

    if not coords:
        return {
            "member_count": len(ids),
            "member_ids": ids,
            "dominant_axis": "",
            "total_length_m": 0.0,
        }

    xs, ys, zs = zip(*coords)
    return {
        "member_count": len(ids),
        "member_ids": ids,
        "dominant_axis": max(axes, key=axes.get),
        "x_min": round(min(xs), 3),
        "x_max": round(max(xs), 3),
        "y_min": round(min(ys), 3),
        "y_max": round(max(ys), 3),
        "y_mid": round((min(ys) + max(ys)) / 2.0, 3),
        "z_min": round(min(zs), 3),
        "z_max": round(max(zs), 3),
        "avg_length_m": round(sum(lengths) / len(lengths), 3) if lengths else 0.0,
        "total_length_m": round(sum(lengths), 3),
    }


def _shelter_member_rows(entries, structural, intensity, group_by_elevation=True,
                          force_backderive_intensity=False):
    """Build Edge/Interior tributary-width rows for a shelter load category (platform, roof,
    or wind face). Presents Member / Tributary Width (with working) / Load Intensity /
    Member Load, collapsing everything
    into role-based rows (no elevation, no per-member listing) because shelter members are
    numerous. group_by_elevation=False ignores the Y level when grouping neighbours - needed
    for sloped/gable roof (and roof-uplift) members that never share an exact Y level; flat
    levels (main platform, wind ledger rows) keep elevation grouping so unrelated rows can't
    contaminate each other's tributary-width calculation.

    force_backderive_intensity=True ignores the passed `intensity` for display purposes and
    always reads the real per-row pressure back from (line load / tributary width) instead -
    needed when the same wind case applies a different pressure at each scaffold lift height
    (EN 1991-1-4 qp(z) varying with elevation) rather than one pressure for the whole
    structure. `intensity` is still used as the last-resort tributary-width estimate for any
    row whose geometric neighbours can't be found."""
    member_entries = [
        {
            "load_case": entry.get("load_case", 0),
            "member_id": entry["member_id"],
            "line_load_kn_m": entry["line_load_kn_m"],
            "geometry": _live_member_geometry(entry["member_id"], structural),
        }
        for entry in entries
    ]
    _resolve_vertical_tributary_axis(member_entries)
    _assign_tributary_widths(member_entries, group_by_elevation=group_by_elevation)

    grouped = {}
    for entry in member_entries:
        line_load = entry["line_load_kn_m"]
        tw = entry.get("tributary_width_m")
        tw_display = entry.get("tributary_width_display")
        role = entry.get("member_role")
        if not tw:
            role = role or "Loaded"
            if not intensity:
                continue
            tw = round(line_load / intensity, 3)
            tw_display = _fmt_width(tw)

        key = (role, tw_display, round(line_load, 3))
        row = grouped.setdefault(key, {
            "count": 0,
            "member_role": role,
            "tributary_width_m": round(tw, 3),
            "tributary_width_display": tw_display,
            "line_load_kn_m": round(line_load, 3),
        })
        row["count"] += 1

    rows = []
    for row in grouped.values():
        if force_backderive_intensity and row["tributary_width_m"]:
            load_intensity = row["line_load_kn_m"] / row["tributary_width_m"]
        else:
            load_intensity = intensity if intensity else (
                row["line_load_kn_m"] / row["tributary_width_m"] if row["tributary_width_m"] else row["line_load_kn_m"]
            )
        row["load_intensity_kn_m2"] = round(load_intensity, 3)
        row.pop("count")
        row["member_display"] = f"{row['member_role']} Members"
        row["working"] = (
            f"{_format_load_value(row['load_intensity_kn_m2'])} x "
            f"{_fmt_width(row['tributary_width_m'])} = {_format_load_value(row['line_load_kn_m'])}"
        )
        rows.append(row)

    # Different rows (e.g. mirrored "(A + B)" vs "(B + A)" interior spans, or separate wind
    # ledger levels in the non-height-varying case) can independently produce the same real
    # bay width/load - one row's neighbours may resolve to Edge/Interior while another falls
    # back to "Loaded". Merge duplicates so the same bay isn't shown twice; a genuinely
    # different pressure tier already has a different real load, so this never merges across
    # tiers even when pressure varies by height.
    consolidated = {}
    for row in rows:
        key = (round(row["tributary_width_m"], 3), round(row["line_load_kn_m"], 3))
        existing = consolidated.get(key)
        if existing is None or (existing["member_role"] == "Loaded" and row["member_role"] != "Loaded"):
            consolidated[key] = row
    rows = list(consolidated.values())

    if force_backderive_intensity:
        # Group visually by pressure tier (low to high) before role/width, since that's
        # what distinguishes one scaffold lift's rows from the next here.
        rows.sort(key=lambda r: (r["load_intensity_kn_m2"], 0 if r["member_role"] == "Edge" else 1, r["tributary_width_m"]))
    else:
        rows.sort(key=lambda r: (0 if r["member_role"] == "Edge" else 1, r["tributary_width_m"], r["line_load_kn_m"]))
    return rows


def _classify_shelter_live_members(project, structural):
    """Classify every STAAD platform-live-load member group into roof, seat, or main
    walking-platform buckets, purely from geometry (roof-band elevation) and UDL magnitude
    (seat UDL match) - no manual overrides. Shared by the live-load working tables and the
    platform-boarding node detector so both agree on which members belong to which zone."""
    seat_line_load = _project_float(project, "SEAT_LIVE_LOAD_KN_M")
    geom = structural.get("geometry", {})
    y_max = geom.get("y_max", geom.get("height", 0.0))
    height = geom.get("height", 0.0)
    roof_band = max(0.5, 0.20 * height)

    roof_members, seat_members, platform_members = set(), set(), set()
    roof_entries, seat_entries, platform_entries = [], [], []
    member_sets = {"roof": roof_members, "seat": seat_members, "platform": platform_members}
    entry_lists = {"roof": roof_entries, "seat": seat_entries, "platform": platform_entries}

    for load in (structural.get("loads", {}) or {}).get("platform_live_member_loads", []):
        members = load.get("members") or []
        summary = _member_group_summary(members, structural)
        line_load = abs(float(load.get("value", 0.0)))

        if summary.get("y_max", 0.0) >= y_max - roof_band:
            category = "roof"
        elif seat_line_load and abs(line_load - seat_line_load) <= max(0.025, seat_line_load * 0.035):
            category = "seat"
        else:
            category = "platform"

        for member_id in members:
            mid = int(member_id)
            member_sets[category].add(mid)
            entry_lists[category].append({
                "member_id": mid,
                "line_load_kn_m": line_load,
                "load_case": load.get("load_case"),
            })

    return {
        "seat_line_load": seat_line_load,
        "roof_members": roof_members, "seat_members": seat_members, "platform_members": platform_members,
        "roof_entries": roof_entries, "seat_entries": seat_entries, "platform_entries": platform_entries,
    }


def _shelter_live_workings(project, structural):
    """Roof, seat-ledger, and main walking-platform live loads for shelter reports.
    Members are classified automatically from STAAD elevations and UDLs - no manual overrides."""
    roof_intensity = _project_float(project, "ROOF_LIVE_LOAD_KN_M2")
    platform_intensity = _project_float(project, "PLATFORM_LIVE_LOAD_KN_M2")

    classified = _classify_shelter_live_members(project, structural)
    seat_line_load = classified["seat_line_load"]
    platform_entries = classified["platform_entries"]
    roof_entries = classified["roof_entries"]
    seat_entries = classified["seat_entries"]

    platform_rows = _shelter_member_rows(platform_entries, structural, platform_intensity, group_by_elevation=True)
    if platform_intensity is None and platform_rows:
        platform_intensity = round(max(r["load_intensity_kn_m2"] for r in platform_rows), 3)
        for row in platform_rows:
            row["load_intensity_kn_m2"] = platform_intensity

    roof_rows = _shelter_member_rows(roof_entries, structural, roof_intensity, group_by_elevation=False)
    seat_member_count = len({e["member_id"] for e in seat_entries})

    # STAAD prints one SUMMATION FORCE-Y per load case, and all three live categories share
    # a single LL case, so it has no per-category split. Each category's total is therefore
    # the sum of UDL x member length over its members - the same arithmetic STAAD itself
    # uses to build the case total, so the three add back up to the STAAD figure.
    members = structural.get("members", {}) or {}

    def _category_total(entries):
        total = 0.0
        for e in entries:
            length_m = (members.get(e["member_id"]) or {}).get("length_mm", 0.0) / 1000.0
            total += e["line_load_kn_m"] * length_m
        # Half-up on the 6dp value: plain round() sends 107.055 to 107.05 (float repr),
        # leaving the displayed category totals a hundredth short of the STAAD total.
        return float(Decimal(str(round(total, 6))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    live_case_totals = (structural.get("loads", {}) or {}).get("platform_live_case_totals") or []
    staad_total = round(sum(c["total_y"] for c in live_case_totals), 2) if live_case_totals else 0.0

    return {
        "roof_intensity_kn_m2": roof_intensity,
        "seat_line_load_kn_m": seat_line_load,
        "platform_total_kn": _category_total(platform_entries),
        "roof_total_kn": _category_total(roof_entries),
        "seat_total_kn": _category_total(seat_entries),
        "staad_total_kn": staad_total,
        "seat_member_count": seat_member_count,
        "platform_intensity_kn_m2": platform_intensity,
        "roof_rows": roof_rows,
        "platform_rows": platform_rows,
    }


def _wind_pressure_varies_by_height(entries, structural):
    """True if members at the same plan position carry different pressure at different
    heights - an EN 1991-1-4 qp(z) pressure schedule evaluated separately per scaffold
    lift - rather than one pressure applied uniformly regardless of elevation."""
    member_entries = [
        {
            "load_case": e.get("load_case", 0),
            "member_id": e["member_id"],
            "line_load_kn_m": e["line_load_kn_m"],
            "geometry": _live_member_geometry(e["member_id"], structural),
        }
        for e in entries
    ]
    _resolve_vertical_tributary_axis(member_entries)

    groups = {}
    for entry in member_entries:
        geom = entry.get("geometry")
        if not geom:
            continue
        key = (entry["load_case"], geom["axis"], geom.get("perp_coord"))
        groups.setdefault(key, set()).add((geom["y_mid"], round(entry["line_load_kn_m"], 3)))

    for pairs in groups.values():
        if len({y for y, _ in pairs}) >= 2 and len({v for _, v in pairs}) >= 2:
            return True
    return False


def _solve_wind_reference_height(target_qw, cf, lo=0.1, hi=200.0, tol=1e-6):
    """Invert qp(z) x Cf = target_qw for z by bisection - qp(z) increases monotonically
    with z (EN 1991-1-4), so this recovers the exact reference height a qw value was
    computed at, the same way solving x from y = f(x) recovers x for any monotonic f."""
    def qw_at(z):
        return WindCalculator(z).calculate()['qp_knm2'] * cf
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if qw_at(mid) < target_qw:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return round((lo + hi) / 2.0, 3)


def _wind_pressure_tiers(row_lists, cf, structure_height=None, gap=0.05):
    """Some projects don't use one wind pressure for the whole structure - they evaluate
    EN 1991-1-4's qp(z) at several reference heights (each measured from ground zero, not
    from the previous lift) and apply the resulting pressure to the standard segments in
    that band. The real per-row pressures already back-derived by _shelter_member_rows are
    literally qp(z) x Cf for whichever z was used - so instead of guessing which STAAD node
    elevation was "the" reference height (the real segment boundaries rarely line up with
    it, e.g. a sloped roof chops the top lift into odd sub-lengths), solve for z directly:
    invert the same EN 1991-1-4 formula this report already uses everywhere else.

    Distinct rows belonging to the same real tier differ only by rounding noise (dividing
    slightly different real loads by slightly different tributary widths), so nearby qw
    values are clustered together (gap-based) before solving, rather than solving each row
    independently and risking two near-identical results that round to different heights.

    Returns (lookup, tiers): `lookup` maps a row's own rounded load_intensity_kn_m2 to
    (reference_height_m, tier_qw) for annotating individual rows; `tiers` is the sorted
    list of (reference_height_m, tier_qw) for the summary table.
    """
    qws = sorted({round(r["load_intensity_kn_m2"], 3) for rows in row_lists for r in rows})
    if not qws:
        return {}, []

    clusters = [[qws[0]]]
    for q in qws[1:]:
        if q - clusters[-1][-1] <= gap:
            clusters[-1].append(q)
        else:
            clusters.append([q])

    lookup = {}
    tiers = []
    for cluster in clusters:
        tier_qw = round(sum(cluster) / len(cluster), 3)
        z = _solve_wind_reference_height(tier_qw, cf)
        tiers.append((z, tier_qw))
        for q in cluster:
            lookup[q] = (z, tier_qw)

    tiers.sort()

    # The topmost tier's reference height is, by definition, the full scaffold height
    # (the tallest standard) - not a value to solve for. Rounding line_load/tributary
    # width to 3dp before back-deriving qw introduces enough error that bisection lands
    # a few mm/cm short of the true height (e.g. 5.994 instead of 6.0), so snap it back
    # once it's already been confirmed close (within one lift's worth of tolerance) -
    # anything further off means this tier isn't actually the roof-height band and is
    # left alone rather than forced.
    if tiers and structure_height is not None and abs(tiers[-1][0] - structure_height) <= 0.5:
        z, tier_qw = tiers[-1]
        tiers[-1] = (round(float(structure_height), 3), tier_qw)
        for q, (old_z, old_qw) in list(lookup.items()):
            if old_z == z:
                lookup[q] = (tiers[-1][0], old_qw)

    return lookup, tiers


def _shelter_wind_pressure(wind):
    """Shelter design wind pressure qw = qp x Cf, generated entirely from the EN 1991-1-4
    calculation (wind.qp_knm2, wind.cf) - never overridden from project_info."""
    pressure = round(float(wind.get("qp_knm2", 0.0) or 0.0) * float(wind.get("cf", 1.0) or 1.0), 3)
    wind["shelter_pressure_kn_m2"] = pressure
    return pressure


def _shelter_wind_workings(structural, wind_pressure, cf):
    """Wind load application on shelter members, presented per face (WLX, WLZ) plus roof
    uplift (WLY), using the same Edge/Interior tributary-width presentation as live loads."""
    lateral_entries = {"X": [], "Z": []}
    uplift_entries = []

    for case in structural.get("load_cases", []):
        if case.get("category") != "wind":
            continue
        for udl in case.get("member_udls", []):
            direction = udl.get("direction")
            line_load = abs(float(udl.get("value", 0.0)))
            entries = [
                {"member_id": int(m), "line_load_kn_m": line_load, "load_case": case.get("number")}
                for m in (udl.get("members") or [])
            ]
            if direction == "Y":
                uplift_entries.extend(entries)
            elif direction in lateral_entries:
                lateral_entries[direction].extend(entries)

    # Some projects evaluate qp(z) separately at each scaffold lift height (EN 1991-1-4
    # pressure genuinely increasing with elevation), each reference height measured from
    # ground zero, instead of applying one pressure for the whole structure - detect that
    # automatically from the real STAAD loads rather than requiring a project_info flag.
    height_varying = (
        _wind_pressure_varies_by_height(lateral_entries["X"], structural)
        or _wind_pressure_varies_by_height(lateral_entries["Z"], structural)
    )

    wind_x_rows = _shelter_member_rows(lateral_entries["X"], structural, wind_pressure,
                                        group_by_elevation=True, force_backderive_intensity=height_varying)
    wind_z_rows = _shelter_member_rows(lateral_entries["Z"], structural, wind_pressure,
                                        group_by_elevation=True, force_backderive_intensity=height_varying)

    height_bands = []
    if height_varying:
        # Every row belonging to the same reference height must display the exact same
        # qw - the summary table's clustered tier value - rather than its own row's
        # back-derived intensity (which can be a rounding-noise hair off, e.g. 1.277 vs
        # 1.278, purely from dividing slightly different real loads/widths). Re-deriving
        # the working from that shared tier value keeps the whole tier reading as one
        # consistent number, at the cost of the working's right-hand side occasionally
        # being a thousandth of a kN off the real STAAD load from rounding - normal and
        # expected when several rows are presented under one representative pressure.
        geom = structural.get("geometry", {}) or {}
        structure_height = geom.get("y_max", geom.get("height"))
        lookup, height_bands = _wind_pressure_tiers([wind_x_rows, wind_z_rows], cf, structure_height=structure_height)
        for row in wind_x_rows + wind_z_rows:
            z, tier_qw = lookup.get(round(row["load_intensity_kn_m2"], 3), (None, None))
            row["reference_height_m"] = z
            if tier_qw is not None:
                row["load_intensity_kn_m2"] = tier_qw
                row["working"] = (
                    f"{_format_load_value(tier_qw)} x "
                    f"{_fmt_width(row['tributary_width_m'])} = {_format_load_value(row['line_load_kn_m'])}"
                )

    return {
        "wind_x_rows": wind_x_rows,
        "wind_z_rows": wind_z_rows,
        "uplift_rows": _shelter_member_rows(uplift_entries, structural, wind_pressure, group_by_elevation=False),
        "height_varying": height_varying,
        "height_bands": height_bands,
    }


def _load_case_total_y(structural, category, fallback_case=None):
    summaries = structural.get("load_summaries", {})
    candidates = [
        case["number"]
        for case in structural.get("load_cases", [])
        if case.get("category") == category
    ]
    if fallback_case is not None:
        candidates.append(fallback_case)
    vals = [summaries.get(number, {}).get("fy", 0.0) for number in candidates]
    return round(max(vals), 3) if vals else 0.0


def _shelter_uplift_resistance(project, structural):
    enabled = _bool_setting(project.get("UPLIFT_RESISTANCE_ENABLED"), True)
    wind_total_y = _project_float(project, "UPLIFT_TOTAL_WLY_KN")
    if wind_total_y is None:
        wind_total_y = (structural.get("wind_loads", {}) or {}).get("total_y", 0.0)

    dead_total = _project_float(project, "UPLIFT_DEAD_LOAD_KN")
    if dead_total is None:
        dead_total = _load_case_total_y(structural, "dead", fallback_case=1)

    anchorage_points = _project_int(project, "UPLIFT_ANCHORAGE_POINTS", default=0)
    block_l = _project_float(project, "CONCRETE_BLOCK_LENGTH_M")
    block_w = _project_float(project, "CONCRETE_BLOCK_WIDTH_M")
    block_h = _project_float(project, "CONCRETE_BLOCK_HEIGHT_M")
    unit_weight = _project_float(project, "CONCRETE_UNIT_WEIGHT_KN_M3")

    required = max(float(wind_total_y or 0.0) - float(dead_total or 0.0), 0.0)
    per_point = required / anchorage_points if anchorage_points else 0.0
    block_volume = (block_l or 0.0) * (block_w or 0.0) * (block_h or 0.0)
    block_weight = block_volume * (unit_weight or 0.0)
    blocks_per_point = math.ceil(per_point / block_weight) if block_weight > 0 and anchorage_points else 0
    total_blocks = blocks_per_point * anchorage_points if anchorage_points else 0
    provided = total_blocks * block_weight

    return {
        "enabled": enabled,
        "wind_uplift_kn": round(float(wind_total_y or 0.0), 3),
        "dead_load_kn": round(float(dead_total or 0.0), 3),
        "required_kn": round(required, 3),
        "anchorage_points": anchorage_points,
        "per_point_kn": round(per_point, 3),
        "block_length_m": block_l,
        "block_width_m": block_w,
        "block_height_m": block_h,
        "block_volume_m3": round(block_volume, 4),
        "unit_weight_kn_m3": unit_weight,
        "block_weight_kn": round(block_weight, 3),
        "blocks_per_point": blocks_per_point,
        "total_blocks": total_blocks,
        "provided_counterweight_kn": round(provided, 3),
        "provided_counterweight_tonnes": round(provided / 9.81, 3) if provided else 0.0,
        "status": "Not required" if required <= 0.001 else ("Calculated" if total_blocks else "Input incomplete"),
    }


def _shelter_occupancy(project, structural, live):
    """Safe occupancy for the main walking platform: design intensity x plan area gives
    the total characteristic live load (independent of any real gap/opening in the STAAD
    model - this is the platform's designed capacity, not what happens to be applied),
    then divided by a nominal per-person mass to get a persons-capacity, taking the most
    conservative (heaviest) mass assumption as the governing safe maximum."""
    geom = structural.get("geometry", {}) or {}
    plan_length = max(geom.get("width", 0.0), geom.get("depth", 0.0))
    plan_width = min(geom.get("width", 0.0), geom.get("depth", 0.0))
    area_m2 = round(plan_length * plan_width, 3)
    intensity = live.get("platform_intensity_kn_m2") or 0.0
    total_load_kn = round(area_m2 * intensity, 3)

    if not (area_m2 and intensity):
        return {"enabled": False}

    mass_tonnes = round(total_load_kn / 9.81, 3)

    mass_list = []
    for token in (_project_value(project, "OCCUPANT_MASSES_KG") or "80,100").split(","):
        token = token.strip()
        if not token:
            continue
        mass = _extract_first_float(token)
        if mass:
            mass_list.append(mass)
    if not mass_list:
        mass_list = [80.0, 100.0]

    rows = []
    for mass_kg in mass_list:
        load_per_person_kn = round(mass_kg / 1000.0 * 9.81, 3)
        capacity = int(total_load_kn // load_per_person_kn) if load_per_person_kn else 0
        rows.append({"mass_kg": mass_kg, "load_per_person_kn": load_per_person_kn, "capacity": capacity})

    return {
        "enabled": True,
        "plan_length_m": plan_length,
        "plan_width_m": plan_width,
        "area_m2": area_m2,
        "intensity_kn_m2": intensity,
        "total_load_kn": total_load_kn,
        "mass_tonnes": mass_tonnes,
        "rows": rows,
        "safe_max_occupancy": min((r["capacity"] for r in rows), default=0),
    }


def _build_shelter_data(project, structural, wind):
    wind_pressure = _shelter_wind_pressure(wind)
    live = _shelter_live_workings(project, structural)
    wind_workings = _shelter_wind_workings(structural, wind_pressure, float(wind.get("cf", 1.0) or 1.0))
    uplift = _shelter_uplift_resistance(project, structural)
    return {
        "tied": _bool_setting(project.get("SHELTER_TIED"), False),
        "live": live,
        "dead_total_kn": _load_case_total_y(structural, "dead", fallback_case=1),
        "occupancy": _shelter_occupancy(project, structural, live),
        "wind": wind_workings,
        "uplift": uplift,
    }


def _brief_description(project, structural, structure_above_ground):
    purpose = str(project.get("PURPOSE") or "the intended work activity").strip()
    scaffold_type = str(project.get("SCAFFOLD_TYPE") or "scaffold").strip()
    scaffold_type = scaffold_type[:1].lower() + scaffold_type[1:] if scaffold_type else scaffold_type
    shelter_use = str(project.get("SHELTER_USE") or "").strip()
    shelter_use = shelter_use[:1].upper() + shelter_use[1:] if shelter_use else shelter_use
    scaffold_type_text = f"{shelter_use} {scaffold_type}".strip() if shelter_use else scaffold_type
    article = _indefinite_article(scaffold_type_text)
    location_text = str(project.get("LOCATION") or "").strip()

    work_order = str(project.get("WORK_ORDER") or "").strip()
    work_order_text = f" under Work Order {work_order}" if work_order else ""
    location_sentence = f" at {location_text}" if location_text else ""
    height_sentence = f" The structure is {structure_above_ground}m above ground level." if structure_above_ground else ""

    has_platforms = any(
        c.get('category') == 'platform_live'
        for c in structural.get('load_cases', [])
    )

    components = ["standards", "ledgers", "transoms", "bracing", "roof shelter framing"]
    if has_platforms:
        components.append("walking platform")
        components.append("seat ledgers")
    if structural.get("shelter", {}).get("tied"):
        components.append("support/tie arrangements")

    if len(components) > 1:
        component_text = ", ".join(components[:-1]) + ", and " + components[-1]
    else:
        component_text = components[0]

    return (
        f"This document describes the structural design of {article} {scaffold_type_text} scaffold required for "
        f"{purpose}{work_order_text}{location_sentence}. "
        f"The scaffold envelope is {structural['dimension_display']} (length x width x height) and "
        f"is configured with {component_text} as indicated on the approved drawing.{height_sentence}"
    )


def _connection_class(max_axial):
    axial = abs(float(max_axial or 0.0))
    if axial <= 10.0:
        return {"class": "Class A", "capacity": 10.0, "status": "PASS", "message": "Class A right-angle couplers are adequate."}
    if axial <= 15.0:
        return {"class": "Class B", "capacity": 15.0, "status": "PASS", "message": "Class B right-angle couplers are required."}
    return {"class": "Review required", "capacity": 15.0, "status": "FAIL", "message": "Applied axial load exceeds the Class B slipping resistance in Table C.1."}


def _normalise_drawing_format(value):
    raw = (value or "standard").strip().lower().replace("_", "-")
    aliases = {
        "generate-scaffold-dxf": "standard",
        "generate-scaffold-grid-dxf": "grid",
        "normal": "standard",
        "plain": "standard",
        "off": "none",
        "no": "none",
    }
    return aliases.get(raw, raw if raw in {"standard", "grid", "none"} else "standard")


def _venv_python(project_dir):
    win_py = project_dir / ".venv" / "Scripts" / "python.exe"
    nix_py = project_dir / ".venv" / "bin" / "python"
    if win_py.exists():
        return win_py
    if nix_py.exists():
        return nix_py
    return Path(sys.executable)


def _console_safe(text):
    encoding = sys.stdout.encoding or "utf-8"
    return str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")


def _print_tail(label, text, max_lines=8):
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return
    print(f"  {_console_safe(label)}:")
    for line in lines[-max_lines:]:
        print(f"    {_console_safe(line)}")


def _run_command(label, command, cwd, timeout=300):
    try:
        result = subprocess.run(
            [str(part) for part in command],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception as exc:
        print(f"  [WARN] {label} failed to start: {exc}")
        return False

    if result.returncode != 0:
        print(f"  [WARN] {label} failed with exit code {result.returncode}")
        _print_tail("stdout", result.stdout)
        _print_tail("stderr", result.stderr)
        return False

    _print_tail(label, result.stdout, max_lines=4)
    return True


def _boarding_quad_corners(node_ids, nodes, x0, x1, z0, z1, y_level=None):
    """Find the actual STAAD node nearest each of the 4 plan corners of the
    (x0,z0)-(x1,z0)-(x1,z1)-(x0,z1) rectangle. y_level restricts the search to nodes near
    that elevation (flat zones); leave it None for a sloped zone, where the nearest node in
    plan is used regardless of its Y (each corner keeps its own real elevation)."""
    by_xz = {}
    for nid in node_ids:
        coord = nodes.get(nid)
        if not coord:
            continue
        if y_level is not None and abs(coord[1] - y_level) > 0.15:
            continue
        by_xz[(coord[0], coord[2])] = nid

    if not by_xz:
        return None

    def _nearest(x, z):
        return min(by_xz.items(), key=lambda kv: (kv[0][0] - x) ** 2 + (kv[0][1] - z) ** 2)[1]

    corners = [_nearest(x0, z0), _nearest(x1, z0), _nearest(x1, z1), _nearest(x0, z1)]
    if len(set(corners)) != 4:
        return None
    return corners


def _order_quad_ccw(quad, nodes):
    import math
    xz = [nodes[n] for n in quad]
    cx = sum(c[0] for c in xz) / 4
    cz = sum(c[2] for c in xz) / 4
    angles = [math.atan2(c[2] - cz, c[0] - cx) for c in xz]
    return [n for _, n in sorted(zip(angles, quad))]


def _member_node_ids(member_ids, members):
    ids = set()
    for mid in member_ids:
        m = members.get(mid)
        if not m:
            continue
        ids.add(m.get("j1"))
        ids.add(m.get("j2"))
    ids.discard(None)
    return ids


def _grid_edge_covers(seg, x0, x1, z0, z1, tol=0.05):
    """True if segment (sx1,sz1,sx2,sz2) runs along one of the 4 boundary edges of
    the (x0,z0)-(x1,z1) cell, spanning that edge's full length (or more)."""
    sx1, sz1, sx2, sz2 = seg
    if abs(sz1 - sz2) < tol and (abs(sz1 - z0) < tol or abs(sz1 - z1) < tol):
        lo, hi = min(sx1, sx2), max(sx1, sx2)
        if lo <= x0 + tol and hi >= x1 - tol:
            return True
    if abs(sx1 - sx2) < tol and (abs(sx1 - x0) < tol or abs(sx1 - x1) < tol):
        lo, hi = min(sz1, sz2), max(sz1, sz2)
        if lo <= z0 + tol and hi >= z1 - tol:
            return True
    return False


def _detect_grid_quads(member_ids, structural):
    """Reconstruct boarded-area quads for an irregular or ring-shaped zone (e.g. a
    perimeter seat bench with an open middle, or a gap where a walkway breaks it) by
    rasterising the member set onto the grid of X/Z coordinates its own nodes define,
    then emitting one quad per grid cell that a real member's edge actually borders.
    An empty cell with an occupied cell on each axis (an implied L-shaped corner, e.g.
    where a front strip and a side strip meet without their own dedicated corner
    member) is filled in too. Unlike a single bounding-box quad, this never paints
    over an area with no real load-bearing member - only 'the part the load covers'."""
    members = structural.get("members", {})
    nodes = structural.get("geometry", {}).get("nodes", {})

    seg_by_level = {}
    for mid in member_ids:
        mem = members.get(mid)
        if not mem:
            continue
        c1, c2 = nodes.get(mem.get("j1")), nodes.get(mem.get("j2"))
        if not c1 or not c2:
            continue
        y1, y2 = round(c1[1], 1), round(c2[1], 1)
        if abs(y1 - y2) > 0.1:
            continue
        ylevel = round((y1 + y2) / 2, 1)
        seg_by_level.setdefault(ylevel, []).append((c1[0], c1[2], c2[0], c2[2]))

    quads = []
    for ylevel, segs in seg_by_level.items():
        xs = sorted({round(x, 2) for x1, z1, x2, z2 in segs for x in (x1, x2)})
        zs = sorted({round(z, 2) for x1, z1, x2, z2 in segs for z in (z1, z2)})
        nx, nz = len(xs) - 1, len(zs) - 1

        occupied = set()
        for i in range(nx):
            for j in range(nz):
                if any(_grid_edge_covers(s, xs[i], xs[i + 1], zs[j], zs[j + 1]) for s in segs):
                    occupied.add((i, j))

        added = True
        while added:
            added = False
            for i in range(nx):
                for j in range(nz):
                    if (i, j) in occupied:
                        continue
                    horiz = (i - 1, j) in occupied or (i + 1, j) in occupied
                    vert = (i, j - 1) in occupied or (i, j + 1) in occupied
                    if horiz and vert:
                        occupied.add((i, j))
                        added = True

        node_xz = {}
        for nid, coord in nodes.items():
            if abs(coord[1] - ylevel) < 0.15:
                node_xz[(round(coord[0], 2), round(coord[2], 2))] = nid

        for (i, j) in occupied:
            x0, x1, z0, z1 = xs[i], xs[i + 1], zs[j], zs[j + 1]
            ns = [node_xz.get((x0, z0)), node_xz.get((x1, z0)),
                  node_xz.get((x1, z1)), node_xz.get((x0, z1))]
            if all(n is not None for n in ns) and len(set(ns)) == 4:
                quads.append(ns)

    return quads


def _detect_shelter_boarding_quads(project, structural):
    """Whole-area boarded zones for the 3D renderer - one quad for the entire main
    walking-platform area and one for the entire seat-ledger area, plus one quad per
    roof plane (two for a gable roof, split at the ridge; one for a mono-pitch/sloped
    roof), each built from the 4 real STAAD nodes forming the corners of that area -
    not one quad per bay."""
    nodes = structural.get("geometry", {}).get("nodes", {})
    members = structural.get("members", {})
    classified = _classify_shelter_live_members(project, structural)

    quads = []  # list of (category, [node_id, node_id, node_id, node_id])

    # Main walking platform is a single continuous filled area - one bounding-box quad.
    platform_node_ids = _member_node_ids(classified["platform_members"], members)
    platform_coords = [nodes[n] for n in platform_node_ids if n in nodes]
    if len(platform_coords) >= 4:
        xs = [c[0] for c in platform_coords]
        zs = [c[2] for c in platform_coords]
        level_y = sum(c[1] for c in platform_coords) / len(platform_coords)
        quad = _boarding_quad_corners(platform_node_ids, nodes, min(xs), max(xs), min(zs), max(zs), y_level=level_y)
        if quad:
            quads.append(("platform", quad))

    # Seat benches typically run around the perimeter with an open middle (and
    # sometimes a walkway gap) - a single bounding-box quad would wrongly paint over
    # the open floor, so reconstruct it cell-by-cell from the real seat members instead.
    for quad in _detect_grid_quads(classified["seat_members"], structural):
        quads.append(("seat", quad))

    roof_node_ids = _member_node_ids(classified["roof_members"], members)
    roof_coords = [nodes[n] for n in roof_node_ids if n in nodes]
    if len(roof_coords) >= 4:
        xs = [c[0] for c in roof_coords]
        zs = [c[2] for c in roof_coords]

        # The ridge is the roof's highest line of nodes. It runs along whichever plan
        # axis has the larger spread among the highest-elevation nodes; split the roof
        # there into its two sloped planes (each still a real-node 4-corner quad). If
        # that ridge sits at the edge of the footprint rather than inside it, this is
        # really a single-plane (mono-pitch) roof, not a two-sided gable - skip the
        # split so it isn't cut into a bogus second sliver. This auto-detects gable vs.
        # sloped from the actual geometry - no project_info type flag needed.
        split_done = False
        y_top = max(c[1] for c in roof_coords)
        ridge_nodes = [nodes[n] for n in roof_node_ids
                       if n in nodes and nodes[n][1] >= y_top - 0.02]
        rxs = [c[0] for c in ridge_nodes]
        rzs = [c[2] for c in ridge_nodes]
        if (max(rxs) - min(rxs)) >= (max(rzs) - min(rzs)):
            span = max(zs) - min(zs)
            ridge_z = sum(rzs) / len(rzs)
            if span > 0 and min(ridge_z - min(zs), max(zs) - ridge_z) > 0.1 * span:
                for z0, z1 in ((min(zs), ridge_z), (ridge_z, max(zs))):
                    quad = _boarding_quad_corners(roof_node_ids, nodes, min(xs), max(xs), z0, z1)
                    if quad:
                        quads.append(("roof", quad))
                split_done = True
        else:
            span = max(xs) - min(xs)
            ridge_x = sum(rxs) / len(rxs)
            if span > 0 and min(ridge_x - min(xs), max(xs) - ridge_x) > 0.1 * span:
                for x0, x1 in ((min(xs), ridge_x), (ridge_x, max(xs))):
                    quad = _boarding_quad_corners(roof_node_ids, nodes, x0, x1, min(zs), max(zs))
                    if quad:
                        quads.append(("roof", quad))
                split_done = True

        if not split_done:
            quad = _boarding_quad_corners(roof_node_ids, nodes, min(xs), max(xs), min(zs), max(zs))
            if quad:
                quads.append(("roof", quad))

    return [(category, _order_quad_ccw(quad, nodes)) for category, quad in quads]


def _write_platforms_txt(project, structural):
    quads = _detect_shelter_boarding_quads(project, structural)
    platforms_path = RENDERER_DIR / "platforms.txt"
    if not quads:
        print("  Platforms : no live-load zones detected; keeping existing platforms.txt")
        return
    try:
        lines = ["#BOARDED_PLATFORMS:"] + [
            f"{category}:{','.join(str(n) for n in quad)}" for category, quad in quads
        ]
        platforms_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f"  Platforms : auto-detected {len(quads)} zone(s) -> platforms.txt")
    except Exception as exc:
        print(f"  [WARN] Could not write platforms.txt: {exc}")


def auto_render_3d_model(std_path):
    renderer = RENDERER_DIR / "scaffold_renderer.py"
    if not renderer.exists():
        print(f"  [WARN] 3D renderer not found: {renderer}")
        return None

    output_path = IMG_DIR / "3d_model.png"
    command = [
        _venv_python(RENDERER_DIR),
        renderer,
        std_path.resolve(),
        "--output",
        output_path.resolve(),
        "--no-jpg",
    ]

    platforms = RENDERER_DIR / "platforms.txt"
    try:
        has_platforms = platforms.exists() and platforms.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        has_platforms = False
    if has_platforms:
        command.extend(["--platforms", platforms.resolve()])

    print("  3D Render : generating images/3d_model.png from STAAD command")
    if _run_command("3D renderer", command, RENDERER_DIR, timeout=420) and output_path.exists():
        return output_path
    return None


def _read_key_value_file(path):
    values = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            values[key.strip().lower()] = value.strip()
    except FileNotFoundError:
        pass
    return values


def _safe_filename(text):
    safe = re.sub(r'[<>:"/\\|?*]+', "-", str(text or "").strip())
    safe = re.sub(r"\s+", " ", safe).strip(" .")
    return safe or "scaffold"


def _latest_pdf_for_suffix(outdir, suffix):
    matches = [p for p in outdir.glob(f"*-{suffix}.pdf") if p.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def collect_engineering_drawings():
    values = _read_key_value_file(DRAWING_DIR / "title_block_values.txt")
    drawing_no = values.get("drawing_number", "scaffold")
    out_folder = Path(values.get("pdf_output_dir", "pdf_output"))
    outdir = out_folder if out_folder.is_absolute() else DRAWING_DIR / out_folder
    drawing_base = _safe_filename(drawing_no)

    items = [
        {"anchor": "drawing-front-view", "title": "Engineering Drawing - Front View", "suffix": "FRONT-VIEW"},
        {"anchor": "drawing-side-view",  "title": "Engineering Drawing - Side View",  "suffix": "SIDE-VIEW"},
        {"anchor": "drawing-plan-view",  "title": "Engineering Drawing - Plan View",  "suffix": "PLAN-VIEW"},
        {"anchor": "drawing-3d-view",    "title": "Engineering Drawing - 3D View",    "suffix": "3D-VIEW"},
    ]

    found = []
    for item in items:
        expected = outdir / f"{drawing_base}-{item['suffix']}.pdf"
        path = expected if expected.exists() else _latest_pdf_for_suffix(outdir, item["suffix"])
        if path and path.exists():
            entry = dict(item)
            entry["path"] = path
            entry["pdf_name"] = path.name
            found.append(entry)
        else:
            print(f"  [WARN] Missing engineering drawing PDF: {expected}")
    return found


def _update_title_block_values(project):
    tbv_path = DRAWING_DIR / "title_block_values.txt"
    try:
        lines = tbv_path.read_text(encoding='utf-8').splitlines() if tbv_path.exists() else []
        overrides = {
            'drawing_number': (project.get('DOCUMENT_NO') or '').strip(),
            'drawing_title':  (project.get('DOCUMENT_NO') or '').strip(),
            'reviewed_by':    (project.get('REVIEWED_BY_NAME') or '').strip(),
            'approved_by':    (project.get('APPROVED_BY_NAME') or '').strip(),
        }
        updated_keys = set()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or '=' not in stripped:
                new_lines.append(line)
                continue
            key = stripped.partition('=')[0].strip()
            if key in overrides:
                new_lines.append(f"{key} = {overrides[key]}")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        for key, val in overrides.items():
            if key not in updated_keys:
                new_lines.append(f"{key} = {val}")
        tbv_path.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
    except Exception as exc:
        print(f"  [WARN] Could not update title_block_values.txt: {exc}")


def generate_engineering_drawings(std_path, drawing_format):
    scripts = {
        "standard": "generate_scaffold_dxf.py",
        "grid": "generate_scaffold_grid_dxf.py",
    }
    script_name = scripts.get(drawing_format)
    if not script_name:
        return []

    script = DRAWING_DIR / script_name
    if not script.exists():
        print(f"  [WARN] Drawing generator not found: {script}")
        return []

    print(f"  Drawings  : generating {drawing_format} PDFs from STAAD command")
    command = [_venv_python(DRAWING_DIR), script, std_path.resolve()]
    _run_command("drawing generator", command, DRAWING_DIR, timeout=240)
    drawings = collect_engineering_drawings()
    print(f"  Drawings  : {len(drawings)}/4 PDFs ready")
    return drawings


def _load_pdf_tools():
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import ArrayObject, NameObject, FloatObject, NullObject
    except ImportError:
        from PyPDF2 import PdfReader, PdfWriter
        from PyPDF2.generic import ArrayObject, NameObject, FloatObject, NullObject
    return PdfReader, PdfWriter, ArrayObject, NameObject, FloatObject, NullObject


def _pdf_anchor_name(target):
    if target is None:
        return None
    return str(target).lstrip("/")


def _pdf_dest_value(value, FloatObject, NullObject):
    return NullObject() if value is None else FloatObject(float(value))


def _pdf_destination(writer, page_num, ArrayObject, NameObject, FloatObject, NullObject, source=None):
    page_ref = writer._pages.get_object()["/Kids"][page_num]
    dest_type = str(getattr(source, "typ", "/Fit") or "/Fit")
    if dest_type == "/XYZ":
        return ArrayObject([
            page_ref,
            NameObject("/XYZ"),
            _pdf_dest_value(getattr(source, "left", None), FloatObject, NullObject),
            _pdf_dest_value(getattr(source, "top", None), FloatObject, NullObject),
            _pdf_dest_value(getattr(source, "zoom", None), FloatObject, NullObject),
        ])
    return ArrayObject([page_ref, NameObject(dest_type)])


def _direct_pdf_link_targets(writer, destinations, ArrayObject, NameObject):
    fixed = 0

    for page in writer.pages:
        for annot_ref in page.get("/Annots", []):
            annot = annot_ref.get_object()
            action = annot.get("/A")

            if action and str(action.get("/S", "/GoTo")) == "/GoTo":
                key = _pdf_anchor_name(action.get("/D"))
                if key in destinations:
                    action[NameObject("/D")] = ArrayObject(list(destinations[key]))
                    fixed += 1
                continue

            key = _pdf_anchor_name(annot.get("/Dest"))
            if key in destinations:
                annot[NameObject("/Dest")] = ArrayObject(list(destinations[key]))
                fixed += 1

    return fixed


def repair_pdf_links(report_pdf):
    try:
        PdfReader, PdfWriter, ArrayObject, NameObject, FloatObject, NullObject = _load_pdf_tools()
    except ImportError:
        return False

    tmp_pdf = report_pdf.with_name(f"{report_pdf.stem}_tmp_links.pdf")
    try:
        reader = PdfReader(str(report_pdf), strict=False)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        page_targets = {}
        destinations = {}
        for name, dest in getattr(reader, "named_destinations", {}).items():
            page_num = reader.get_destination_page_number(dest)
            if page_num is None:
                continue
            writer.add_named_destination(str(name), page_num)
            key = str(name).lstrip("/")
            page_targets[key] = page_num
            destinations[key] = _pdf_destination(
                writer, page_num, ArrayObject, NameObject, FloatObject, NullObject, dest
            )

        for anchor, title in REPORT_OUTLINE:
            page_num = page_targets.get(anchor)
            if page_num is not None:
                writer.add_outline_item(title, page_num)

        fixed = _direct_pdf_link_targets(writer, destinations, ArrayObject, NameObject)
        with open(tmp_pdf, "wb") as fout:
            writer.write(fout)
        tmp_pdf.replace(report_pdf)
        print(f"  PDF   ->  repaired {fixed} internal links")
        return True
    except Exception as exc:
        print(f"  [WARN] Could not repair PDF links: {exc}")
        try:
            tmp_pdf.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _load_pdf_page_font(size, bold=False):
    from PIL import ImageFont

    names = ["arialbd.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "Arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def create_landscape_image_pdf(image_path, output_pdf, title):
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError:
        print("  [WARN] Install Pillow to append the large 3D model page: pip install Pillow")
        return False

    page_w, page_h = 1754, 1240  # A4 landscape at 150 dpi
    margin = 70
    header_h = 110
    navy = (9, 43, 74)
    gold = (205, 157, 37)
    border = (126, 160, 196)

    canvas = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, page_w, header_h], fill=navy)
    draw.rectangle([0, header_h - 10, page_w, header_h], fill=gold)

    title_font = _load_pdf_page_font(38, bold=True)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_box[2] - title_box[0]
    title_h = title_box[3] - title_box[1]
    draw.text(((page_w - title_w) / 2, (header_h - title_h) / 2 - 4), title, fill="white", font=title_font)

    with Image.open(image_path) as src:
        src = ImageOps.exif_transpose(src)
        if src.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", src.size, "white")
            bg.paste(src, mask=src.split()[-1])
            src = bg
        else:
            src = src.convert("RGB")

        area_w = page_w - (2 * margin)
        area_h = page_h - header_h - (2 * margin)
        resample = getattr(Image, "Resampling", Image).LANCZOS
        fitted = ImageOps.contain(src, (area_w, area_h), resample)
        x = margin + (area_w - fitted.width) // 2
        y = header_h + margin + (area_h - fitted.height) // 2
        draw.rectangle([margin, header_h + margin, page_w - margin, page_h - margin], outline=border, width=3)
        canvas.paste(fitted, (x, y))

    canvas.save(output_pdf, "PDF", resolution=150.0)
    return True


def append_engineering_drawings(report_pdf, drawings, model_image_path=None):
    valid = [d for d in drawings if Path(d.get("path", "")).exists()]
    if not valid:
        return False

    try:
        PdfReader, PdfWriter, ArrayObject, NameObject, FloatObject, NullObject = _load_pdf_tools()
    except ImportError:
        print("  [WARN] Install pypdf to append drawing PDFs automatically: pip install pypdf")
        return False

    tmp_pdf = report_pdf.with_name(f"{report_pdf.stem}_tmp_with_drawings.pdf")
    model_page_pdf = report_pdf.with_name(f"{report_pdf.stem}_tmp_3d_model_page.pdf")
    model_appended = False
    try:
        writer = PdfWriter()
        base_reader = PdfReader(str(report_pdf), strict=False)
        for page in base_reader.pages:
            writer.add_page(page)

        page_targets = {}
        destinations = {}
        for name, dest in getattr(base_reader, "named_destinations", {}).items():
            if str(name).lstrip("/").startswith("drawing-"):
                continue
            page_num = base_reader.get_destination_page_number(dest)
            if page_num is None:
                continue
            writer.add_named_destination(str(name), page_num)
            key = str(name).lstrip("/")
            page_targets[key] = page_num
            destinations[key] = _pdf_destination(
                writer, page_num, ArrayObject, NameObject, FloatObject, NullObject, dest
            )

        for anchor, title in REPORT_OUTLINE:
            page_num = page_targets.get(anchor)
            if page_num is not None:
                writer.add_outline_item(title, page_num)

        for drawing in valid:
            start_page = len(writer.pages)
            reader = PdfReader(str(drawing["path"]), strict=False)
            for page in reader.pages:
                writer.add_page(page)
            writer.add_named_destination(f"/{drawing['anchor']}", start_page)
            writer.add_outline_item(drawing["title"], start_page)
            page_targets[drawing["anchor"]] = start_page
            destinations[drawing["anchor"]] = _pdf_destination(
                writer, start_page, ArrayObject, NameObject, FloatObject, NullObject
            )

        if model_image_path and Path(model_image_path).exists():
            if create_landscape_image_pdf(model_image_path, model_page_pdf, "3D Isometric View"):
                start_page = len(writer.pages)
                model_reader = PdfReader(str(model_page_pdf), strict=False)
                for page in model_reader.pages:
                    writer.add_page(page)
                writer.add_named_destination("/large-3d-model", start_page)
                writer.add_outline_item("3D Isometric View - Large", start_page)
                model_appended = True

        fixed = _direct_pdf_link_targets(writer, destinations, ArrayObject, NameObject)

        with open(tmp_pdf, "wb") as fout:
            writer.write(fout)
        tmp_pdf.replace(report_pdf)
        try:
            model_page_pdf.unlink(missing_ok=True)
        except Exception:
            pass
        model_msg = "; appended large 3D model page" if model_appended else ""
        print(f"  PDF   ->  appended {len(valid)} engineering drawing PDFs{model_msg}; repaired {fixed} internal links")
        return True
    except Exception as exc:
        print(f"  [WARN] Could not append engineering drawings: {exc}")
        try:
            tmp_pdf.unlink(missing_ok=True)
            model_page_pdf.unlink(missing_ok=True)
        except Exception:
            pass
        return False


# -- Installation note generator -----------------------------------------------


def make_install_notes(structural, project=None):
    project = project or {}
    g  = structural['geometry']
    s  = structural['supports']
    W, D, H = g['width'], g['depth'], g['height']
    kicker  = g['kicker_lift']
    mids    = g['mid_lifts']
    tie_h   = s.get('tie_heights', [H])
    tie_n   = s.get('tie_nodes', [])
    scaffold_type = str(project.get('SCAFFOLD_TYPE', 'scaffold')).strip() or 'scaffold'
    purpose = str(project.get('PURPOSE', 'the approved task')).strip() or 'the approved task'

    notes = [
        "The scaffold working drawings and purpose of the scaffold must be reviewed and "
        "discussed by all personnel involved prior to execution.",
        f"Confirm that the {scaffold_type} scaffold configuration matches the approved drawing "
        f"and is suitable for {purpose}.",
        "The work vicinity must be barricaded and appropriate signage placed at all access points.",
        "All scaffolders must wear complete PPE in accordance with NLNG work-at-height regulations.",
        "A valid work permit must be obtained, discussed, and signed before erection commences.",
        "Scaffold erection must be carried out in strict accordance with NASC guidance and site "
        "safety procedures.",
    ]

    notes += [
        "Set out and level the scaffold base plates and sole boards in accordance with "
        "the approved working drawing.",
        f"Confirm the scaffold footprint/envelope is approximately {W:.1f}m x {D:.1f}m x {H:.1f}m "
        "or as otherwise dimensioned on the approved drawing.",
        f"Erect scaffold tube standards (48.3 x 3.6 mm), ledgers, and transoms progressively "
        f"from the base, checking plumb and level in both axes before proceeding to the next lift.",
        f"Install the lower horizontal ledgers and transoms at the kicker lift height "
        f"({kicker:.3f}m) to form the first stable frame.",
    ]

    # Sloped/gable roof geometry can produce dozens of distinct mid-lift elevations (one per
    # purlin along the slope). Cluster levels within 0.15m of each other into a single phrase
    # so the note stays a single sentence instead of repeating near-identical lines.
    if mids:
        clusters = [[mids[0]]]
        for ml in sorted(mids)[1:]:
            if ml - clusters[-1][-1] <= 0.15:
                clusters[-1].append(ml)
            else:
                clusters.append([ml])

        phrases = []
        for cluster in clusters:
            if len(cluster) == 1:
                phrases.append(f"{cluster[0]:.1f}m")
            else:
                phrases.append(f"{cluster[0]:.1f}m to {cluster[-1]:.1f}m (progressively, following the roof slope)")

        heights_text = phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + f" and {phrases[-1]}"
        notes.append(
            f"Install mid-level horizontal ledgers and transoms at {heights_text} in "
            f"accordance with the working drawing."
        )

    notes += [
        "Install all plan, face, and longitudinal bracing shown on the approved drawing to provide "
        "sway resistance in both principal directions.",
        "Install platform boards, guardrails, mid-rails, toe boards, and access arrangements "
        "as required by the design.",
        "Tighten and torque-check all load-bearing couplers and support connections before the "
        "scaffold is released for inspection.",
    ]

    if tie_n:
        tie_str = ' and '.join(f'{h:.1f}m' for h in tie_h)
        notes.append(
            f"Gravlock or box-tie the scaffold structure to the existing structure at all "
            f"indicated tie points at {tie_str} height as shown on the working drawing."
        )

    notes += [
        "The scaffold structure must be inspected and tagged by a competent advance scaffold "
        "inspector after erection and before use.",
        "The safe working load (SWL) stated on the design report must not be exceeded at any "
        "time during operations.",
        "All modifications made after erection must be carried out by a competent scaffold team "
        "with the approval of the scaffold engineer. End-user or third-party modification "
        "of this scaffold structure is strictly prohibited.",
        "For dismantling, perform the erection steps in reverse order.",
    ]
    return notes


# -- Main ----------------------------------------------------------------------

def main():
    from jinja2 import Environment, FileSystemLoader

    args = parse_args()
    OUT_DIR.mkdir(exist_ok=True)

    print("=== Scaffold Report Generator ===\n")

    # -- 1. Project info -------------------------------------------------------
    project = parse_project_info(INPUTS / 'project_info.txt')
    print(f"  Project : {project['DOCUMENT_NO']}")

    structure_above_ground = _optional_float(project.get('STRUCTURE_ABOVE_GROUND_M'))
    if project.get('STRUCTURE_ABOVE_GROUND_M', '').strip() and structure_above_ground is None:
        print("  [WARN] STRUCTURE_ABOVE_GROUND_M is not numeric; cover sentence skipped")

    # -- 2. STAAD parsing ------------------------------------------------------
    std_path = INPUTS / 'staad_command.txt'
    out_path = INPUTS / 'staad_output.txt'

    for p in (std_path, out_path):
        if not p.exists():
            print(f"  [ERROR] Missing: {p}")
            print("  Copy your STAAD .std/.out file contents into inputs/")
            sys.exit(1)

    print("  Parsing STAAD files ...")
    parser     = StaadParser(str(std_path), str(out_path))
    structural = parser.parse()
    g          = structural['geometry']

    drawing_format = _normalise_drawing_format(
        args.drawing_format or project.get("ENGINEERING_DRAWING_FORMAT")
    )

    if not args.skip_3d_render and _bool_setting(project.get("AUTO_RENDER_3D_MODEL"), True):
        _write_platforms_txt(project, structural)
        auto_render_3d_model(std_path)

    engineering_drawings = []
    if (
        not args.skip_engineering_drawings
        and _bool_setting(project.get("AUTO_ENGINEERING_DRAWINGS"), True)
        and drawing_format != "none"
    ):
        _update_title_block_values(project)
        engineering_drawings = generate_engineering_drawings(std_path, drawing_format)
    print(f"  Scaffold  : {g['width']:.1f}m W x {g['depth']:.1f}m D x {g['height']:.1f}m H")

    # -- 3. Wind calculation ---------------------------------------------------
    wind_height_override = _optional_float(project.get('WIND_CALC_HEIGHT_M'))
    if project.get('WIND_CALC_HEIGHT_M', '').strip() and wind_height_override is None:
        print("  [WARN] WIND_CALC_HEIGHT_M is not numeric; falling back to STAAD height")
    wind_height = wind_height_override if wind_height_override is not None else g['height']
    print(f"  Wind calc : z = {_format_number(wind_height)}m ...")
    wind = WindCalculator(wind_height).calculate()
    print(f"             qp = {wind['qp_nm2']:.2f} N/m2")

    # -- 4. Logos & images -----------------------------------------------------
    nlng_logo    = load_logo('nlng')
    company_logo = load_logo('company')
    site_photo = load_image('site_photo')   # no placeholder if missing - intentional
    images = {k: load_image(k) for k in [
        '3d_model',
        'load_platform_live',
        'load_wind_x', 'load_wind_y', 'load_wind_z',
        'connection_table',
        'deflection_vertical_table', 'deflection_horizontal_table',
    ]}
    loaded = sum(1 for v in images.values() if v)
    print(f"  Images    : {loaded}/{len(images)} found")

    # -- 5. Derived values -----------------------------------------------------
    geom = structural['geometry']
    plan_length = max(geom['width'], geom['depth'])
    plan_width = min(geom['width'], geom['depth'])
    structural['dimension_display'] = (
        f"{_format_number(plan_length)}m x {_format_number(plan_width)}m x {_format_number(geom['height'])}m"
    )
    structural['shelter'] = _build_shelter_data(project, structural, wind)
    swl_kn_m2 = structural['shelter']['live'].get('platform_intensity_kn_m2') or 0.0
    structural['swl_kn_m2'] = swl_kn_m2
    structural['swl_display'] = _format_load_value(swl_kn_m2)
    structural['swl_load_class'] = _load_class_for_intensity(swl_kn_m2)
    structural['brief_description'] = _brief_description(
        project,
        structural,
        _format_number(structure_above_ground),
    )
    show_assurance_note = _bool_setting(
        _project_value(project, 'CATEGORY_1_ASSURANCE_NOTE'),
        False
    )
    shelter_tied = bool(structural['shelter'].get('tied'))
    show_tie_reactions = shelter_tied and _bool_setting(project.get('SHOW_TIE_REACTIONS'), False)

    # Cover page tie force display — sum (default) or worst single node
    sr = structural.get('support_reactions', {})
    worst_tie     = sr.get('worst_individual_tie')
    net_governing = sr.get('net_global', {}).get('governing')
    tie_display_mode = (project.get('TIE_DISPLAY') or 'sum').strip().lower()
    if tie_display_mode not in ('sum', 'worst'):
        tie_display_mode = 'sum'
    # Legacy scalar variables kept so template fallback still works
    if tie_display_mode == 'worst' and worst_tie:
        tie_sum_fx = worst_tie['max_fx']
        tie_sum_fz = worst_tie['max_fz']
    elif net_governing:
        tie_sum_fx = net_governing['total_x']
        tie_sum_fz = net_governing['total_z']
    else:
        tie_sum_fx = worst_tie['max_fx'] if worst_tie else None
        tie_sum_fz = worst_tie['max_fz'] if worst_tie else None

    if _optional_float(project.get('TIE_FORCE_FX')) is not None:
        tie_sum_fx = _optional_float(project.get('TIE_FORCE_FX'))
    if _optional_float(project.get('TIE_FORCE_FZ')) is not None:
        tie_sum_fz = _optional_float(project.get('TIE_FORCE_FZ'))

    if not shelter_tied:
        tie_sum_fx = None
        tie_sum_fz = None

    # -- Deflection L: look up member length from STAAD geometry -----------------
    members_dict = structural.get('members', {})
    d = structural['displacements']

    def _span_from_node_auto(node_id, fallback_mm):
        """Longest member connected to the critical-displacement node."""
        if node_id:
            lengths = [m['length_mm'] for m in members_dict.values()
                       if m.get('j1') == node_id or m.get('j2') == node_id]
            if lengths:
                return max(lengths)
        return fallback_mm

    def _member_length_mm(member_key, fallback_mm):
        try:
            mid = int(project.get(member_key, 0) or 0)
            if mid and mid in members_dict:
                return members_dict[mid]['length_mm']
        except (ValueError, TypeError):
            pass
        return fallback_mm

    vert_span_mm  = _member_length_mm('MAX_VERT_MEMBER',
                        _span_from_node_auto(d.get('max_vertical_node'),  geom['width'] * 1000))
    horiz_span_mm = _member_length_mm('MAX_HORIZ_MEMBER',
                        _span_from_node_auto(d.get('max_horizontal_node'), geom['depth'] * 1000))
    vert_allow    = round(vert_span_mm  / 100, 1)
    horiz_allow   = round(horiz_span_mm / 200, 1)

    # Member details for report display
    def _member_info(member_key, auto_node=None):
        try:
            mid = int(project.get(member_key, 0) or 0)
            if mid and mid in members_dict:
                return {'id': mid, 'length_mm': members_dict[mid]['length_mm']}
        except:
            pass
        if auto_node:
            connected = [(mid, m['length_mm']) for mid, m in members_dict.items()
                         if m.get('j1') == auto_node or m.get('j2') == auto_node]
            if connected:
                best_mid, best_len = max(connected, key=lambda x: x[1])
                return {'id': best_mid, 'length_mm': best_len}
        return None

    vert_member_info  = _member_info('MAX_VERT_MEMBER',  d.get('max_vertical_node'))
    horiz_member_info = _member_info('MAX_HORIZ_MEMBER', d.get('max_horizontal_node'))

    # -- Connection stability: max axial in HORIZONTAL members only (coupler slipping) --
    def _float(val, fallback):
        try: return float(val) if val else fallback
        except: return fallback

    nodes_coord = structural.get('geometry', {}).get('nodes', {})

    def _is_horizontal(member_id):
        """True only for genuine ledgers/transoms: level (Y is effectively constant
        along the member) and a real coupler-jointed tube length. A simple 'run exceeds
        rise' test also catches sloped roof rafters/purlins (any incline where the
        horizontal run is bigger than the rise still passes) and tiny sub-100mm mesh
        segments within the roof framing, both of which can carry disproportionate axial
        force and are not couplers this check applies to."""
        m = members_dict.get(member_id)
        if not m:
            return True
        n1, n2 = nodes_coord.get(m['j1']), nodes_coord.get(m['j2'])
        if not n1 or not n2:
            return True
        if m.get('length_mm', 0.0) < 300:
            return False
        return abs(n2[1] - n1[1]) < 0.01

    # Real per-member, per-load-case axial force, from a STAAD 'PRINT MEMBER FORCES'
    # table (not the steel code-check block: the code-check axial is tied to whichever
    # load case governs that member's bending/combined-stress UC ratio, not necessarily
    # the load case with the largest raw axial force - which is what actually matters
    # for a coupler slipping check).
    member_forces = structural.get('member_forces') or {}
    combos = structural.get('load_combinations', [])

    def _combo_basis(combo):
        """ULS if the combo title says so, else SLS; falls back to inspecting the load
        factors (ULS combos here are always 1.5x, SLS combos always 1.0x) for projects
        whose combo titles don't carry an explicit ULS/SLS prefix."""
        title = str(combo.get('title', '')).strip().upper()
        if title.startswith('ULS'):
            return 'ULS'
        if title.startswith('SLS'):
            return 'SLS'
        factors = combo.get('factors', [])
        if factors and all(abs(abs(f) - 1.0) < 0.01 for _, f in factors):
            return 'SLS'
        return 'ULS'

    uls_lc_numbers = {c['number'] for c in combos if _combo_basis(c) == 'ULS'}
    sls_lc_numbers = {c['number'] for c in combos if _combo_basis(c) == 'SLS'}

    def _peak_axial(per_load, lc_numbers):
        """(abs_axial, signed_axial, node, load_case) of the largest-magnitude axial
        among the given load cases, or None if none apply."""
        candidates = [(abs(v[0]), v[0], v[1], lc) for lc, v in per_load.items() if lc in lc_numbers]
        return max(candidates, key=lambda t: t[0]) if candidates else None

    axial_source = 'member_forces'
    uls_rows = []
    for mid, per_load in member_forces.items():
        if not _is_horizontal(mid):
            continue
        peak = _peak_axial(per_load, uls_lc_numbers)
        if peak is None:
            continue
        abs_v, signed_v, node, lc = peak
        uls_rows.append({'member': mid, 'axial': round(abs_v, 3), 'node': node, 'lc': lc})
    uls_rows.sort(key=lambda r: r['axial'], reverse=True)

    best = uls_rows[0]
    auto_axial, auto_axial_member = best['axial'], best['member']
    top_axial_members = uls_rows[:30]

    # Manual override (mirrors the deflection-check pattern): auto-computed above from
    # the STAAD output; override only if that computation can't be trusted for a project.
    override_axial = _optional_float(project.get('MAX_AXIAL_KN'))
    if override_axial is not None:
        auto_axial        = override_axial
        override_member   = _optional_float(project.get('MAX_AXIAL_MEMBER'))
        auto_axial_member = int(override_member) if override_member is not None else auto_axial_member
        axial_source      = 'manual'
        top_axial_members = [{
            'member': auto_axial_member, 'node': project.get('MAX_AXIAL_NODE') or '',
            'axial': round(override_axial, 3), 'lc': project.get('MAX_AXIAL_LC') or '',
        }]

    # Check ULS first; if the coupler class fails under ULS, fall back to SLS (unfactored,
    # gamma=1.0 — see Load Combinations legend). This is a fallback verification basis, not
    # a substitute UC check — the Status/Clause/UC Ratio columns are ULS-specific and are
    # not shown for the SLS view.
    connection_basis = 'ULS'
    max_axial        = auto_axial
    max_axial_member = str(auto_axial_member or '')
    connection_class = _connection_class(max_axial)

    override_sls_axial = _optional_float(project.get('MAX_AXIAL_SLS_KN'))
    if connection_class['status'] == 'FAIL':
        connection_basis = 'SLS'
        if override_sls_axial is not None:
            override_sls_member = _optional_float(project.get('MAX_AXIAL_SLS_MEMBER'))
            max_axial        = round(override_sls_axial, 3)
            max_axial_member = str(int(override_sls_member) if override_sls_member is not None else (auto_axial_member or ''))
            sls_lc           = project.get('MAX_AXIAL_SLS_LC') or (top_axial_members[0]['lc'] if top_axial_members else '')
            sls_node         = project.get('MAX_AXIAL_SLS_NODE') or (top_axial_members[0].get('node', '') if top_axial_members else '')
            axial_source     = 'manual'
            top_axial_members = [{
                'member': max_axial_member, 'node': sls_node,
                'axial': max_axial, 'lc': sls_lc,
            }]
        elif axial_source == 'member_forces':
            # Look up the SAME governing member's real SLS-combo axial directly - exact,
            # no unfactoring needed.
            peak = _peak_axial(member_forces.get(auto_axial_member, {}), sls_lc_numbers)
            if peak is not None:
                abs_v, signed_v, node, lc = peak
                max_axial = round(abs_v, 3)

            sls_rows = []
            for row in top_axial_members:
                peak = _peak_axial(member_forces.get(row['member'], {}), sls_lc_numbers)
                if peak is not None:
                    abs_v, signed_v, node, lc = peak
                    sls_rows.append({'member': row['member'], 'axial': round(abs_v, 3),
                                      'node': node, 'lc': lc})
                else:
                    sls_rows.append({**row, 'axial': round(row['axial'] / 1.5, 3)})
            sls_rows.sort(key=lambda r: r['axial'], reverse=True)
            top_axial_members = sls_rows
        else:
            # Manual-override fallback (no MAX_AXIAL_SLS_KN given): approximate SLS force
            # as ULS force / 1.5, since every ULS combo here is the same SLS combo at 1.5x.
            max_axial = round(auto_axial / 1.5, 3)
            top_axial_members = [
                {**m, 'axial': round(m['axial'] / 1.5, 3)}
                for m in top_axial_members
            ]
        connection_class = _connection_class(max_axial)

    # -- Deflection values (auto from .out file; project_info keys are optional overrides) --
    max_vert_mm   = _float(project.get('MAX_VERT_DISP_MM'),  d['max_vertical_mm'])
    max_vert_lc   = project.get('MAX_VERT_DISP_LC',  '')  or str(d['max_vertical_lc'])
    max_horiz_mm  = _float(project.get('MAX_HORIZ_DISP_MM'), d['max_horizontal_mm'])
    max_horiz_lc  = project.get('MAX_HORIZ_DISP_LC', '')  or str(d['max_horizontal_lc'])

    install_notes = make_install_notes(structural, project)
    date_gen = datetime.now().strftime('%d-%b-%Y')

    # -- 6. Render template ----------------------------------------------------
    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)))
    env.globals.update({
        'round': round,
        'abs':   abs,
    })

    template = env.get_template('report.html')
    html = template.render(
        project       = project,
        structural    = structural,
        wind          = wind,
        nlng_logo     = nlng_logo,
        company_logo  = company_logo,
        images        = images,
        vert_allow    = vert_allow,
        horiz_allow   = horiz_allow,
        show_assurance_note = show_assurance_note,
        show_tie_reactions = show_tie_reactions,
        tie_sum_fx        = tie_sum_fx,
        tie_sum_fz        = tie_sum_fz,
        tie_display_mode  = tie_display_mode,
        worst_tie         = worst_tie,
        install_notes = install_notes,
        date_gen      = date_gen,
        max_axial        = max_axial,
        max_axial_member = max_axial_member,
        connection_class  = connection_class,
        connection_basis  = connection_basis,
        top_axial_members = top_axial_members,
        max_vert_mm      = max_vert_mm,
        max_vert_lc      = max_vert_lc,
        max_horiz_mm     = max_horiz_mm,
        max_horiz_lc     = max_horiz_lc,
        vert_span_mm      = vert_span_mm,
        vert_member_info  = vert_member_info,
        horiz_span_mm     = horiz_span_mm,
        horiz_member_info = horiz_member_info,
        site_photo       = site_photo,
        engineering_drawings = engineering_drawings,
    )

    # -- 7. Save HTML ----------------------------------------------------------
    doc = project['DOCUMENT_NO'].replace('/', '_')
    html_path = OUT_DIR / f'{doc}_Report.html'
    html_path.write_text(html, encoding='utf-8')
    print(f"\n  HTML  ->  {html_path}")

    # -- 8. PDF generation - 3 engines in order -------------------------------
    pdf_path = OUT_DIR / f'{doc}_Report.pdf'
    _ok = False

    # Engine 1: Playwright (if chromium was previously downloaded)
    if not _ok:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                br   = pw.chromium.launch()
                page = br.new_page()
                page.goto(f'file:///{html_path.resolve().as_posix()}')
                page.wait_for_load_state('networkidle')
                page.pdf(path=str(pdf_path), format='A4',
                         print_background=True,
                         display_header_footer=False,
                         margin={'top':'0mm','bottom':'0mm',
                                 'left':'0mm','right':'0mm'})
                br.close()
            print(f"  PDF   ->  {pdf_path}  [via Playwright]")
            _ok = True
        except Exception:
            pass

    # Engine 2: System Chrome / Edge (no install needed)
    if not _ok:
        _ok = _try_system_browser(html_path, pdf_path)

    # Engine 3: xhtml2pdf (pip install xhtml2pdf - pure Python, no binary)
    if not _ok:
        try:
            from xhtml2pdf import pisa
            resolved = _resolve_css_vars(html_path.read_text(encoding='utf-8'))
            with open(pdf_path, 'wb') as fout:
                pisa.CreatePDF(resolved, dest=fout)
            print(f"  PDF   ->  {pdf_path}  [via xhtml2pdf]")
            _ok = True
        except ImportError:
            pass
        except Exception as e:
            print(f"  [WARN] xhtml2pdf error: {e}")

    if not _ok:
        print("\n  HTML saved. To get a PDF, choose one:")
        print("  A) pip install xhtml2pdf        (pure Python, no extra downloads)")
        print("  B) playwright install chromium   (best quality, one-time ~150 MB)")
        print("  C) Open HTML in Chrome/Edge -> Ctrl+P -> Save as PDF")
    else:
        show_3d_iso = _bool_setting(project.get("SHOW_3D_ISOMETRIC_PAGE"), True)
        model_img = find_image_file('3d_model') if show_3d_iso else None
        if engineering_drawings or model_img:
            append_engineering_drawings(pdf_path, engineering_drawings, model_img)
        else:
            repair_pdf_links(pdf_path)

    print("\nDone.\n")


if __name__ == '__main__':
    main()
