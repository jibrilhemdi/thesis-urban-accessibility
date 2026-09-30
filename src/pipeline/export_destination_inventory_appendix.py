"""Read-only export of the frozen Phase 5 canonical OSM destination universe.

Run: .venv/bin/python -m src.pipeline.export_destination_inventory_appendix
Only PostGIS SELECTs are used. No accessibility features or models are rebuilt.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import text

from src.db.connection import get_engine
from src.pipeline.export_final_latex_tables import line, longtable, num, save, tex
from src.pipeline.osm_taxonomy_phase5 import (
    CULTURE_AMENITIES, CULTURE_HISTORIC, CULTURE_TOURISM, FOOD_AMENITIES,
    STATION_RAILWAY, TAXONOMY_VERSION, categories, station_mode,
)


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "outputs/tables/final"
SUPPLEMENT = ROOT / "outputs/tables/supplementary"
LATEX = ROOT / "outputs/latex/appendix"
REPORT = ROOT / "reports/appendix_destination_inventory.md"
GROUPS = ("food_social", "cultural_tourist", "station")
FOOD_ORDER = ("restaurant", "cafe", "bar", "pub")
CULTURE_ORDER = ("museum", "gallery", "attraction", "viewpoint", "theatre", "monument", "castle", "palace")
MODE_ORDER = ("metro", "urban_rail", "rail")
REF_COLUMNS = ("canonical_destination_id", "canonical_name", "destination_group", "osm_subtype",
               "all_qualifying_osm_tags",
               "osm_element_type", "preferred_osm_id", "all_source_osm_refs", "wikidata_id",
               "longitude", "latitude", "inside_study_union", "source_version",
               "taxonomy_version", "deduplication_provenance")


def read_database() -> tuple[list[dict], dict]:
    """Read canonical records and source links in one repeatable-read snapshot."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            source = conn.execute(text(
                "SELECT DISTINCT p.source_file_id,f.filename,f.relative_path,f.source_url,"
                "f.geographic_extent,f.source_date,f.acquisition_date,"
                "f.file_hash_sha256,p.taxonomy_version FROM spatial.osm_pois p "
                "JOIN meta.source_files f USING(source_file_id)"
            )).mappings().all()
            station_sources = conn.execute(text(
                "SELECT DISTINCT source_file_id,taxonomy_version FROM spatial.transit_stations"
            )).all()
            if len(source) != 1 or len(station_sources) != 1:
                raise ValueError("Expected exactly one frozen POI and station source/version")
            src = dict(source[0])
            if (station_sources[0][0], station_sources[0][1]) != (src["source_file_id"], TAXONOMY_VERSION) \
                    or src["taxonomy_version"] != TAXONOMY_VERSION:
                raise ValueError("Phase 5 source or taxonomy does not match phase05_v2")

            # Use the same official two-municipality union and ST_Covers predicate
            # as the already-run boundary sensitivity; this labels destinations
            # but does not filter the primary buffered destination universe.
            common = (
                "d.source_file_id,d.taxonomy_version,d.osm_type,d.osm_id,d.name,d.tags,"
                "d.merged_osm_refs,d.duplicate_count,d.position_method,"
                "ST_X(d.geom) AS longitude,ST_Y(d.geom) AS latitude,"
                "ST_SRID(d.geom) AS srid_wgs84,ST_SRID(d.geom_25832) AS srid_metric,"
                "ST_Covers(u.geom_25832,d.geom_25832) AS inside_study_union,"
                "(SELECT min(m.municipality_name) FROM spatial.official_municipalities m "
                " WHERE m.municipality_code IN ('0101','0147') "
                " AND ST_Covers(m.geom_25832,d.geom_25832)) AS study_municipality "
            )
            poi_query = ("SELECT 'poi' AS kind,d.destination_key AS canonical_id,d.category AS destination_group,"
                         "NULL::text AS mode," + common +
                         "FROM spatial.osm_pois d CROSS JOIN spatial.study_union_boundary_sensitivity u "
                         "ORDER BY d.category,d.destination_key")
            station_query = ("SELECT 'station' AS kind,d.station_key AS canonical_id,"
                             "'station' AS destination_group,d.station_mode AS mode," + common +
                             "FROM spatial.transit_stations d CROSS JOIN spatial.study_union_boundary_sensitivity u "
                             "ORDER BY d.station_key")
            canonical = [dict(row) for row in conn.execute(text(poi_query)).mappings()]
            canonical.extend(dict(row) for row in conn.execute(text(station_query)).mappings())
            candidates = [dict(row) for row in conn.execute(text(
                "SELECT candidate_key,canonical_candidate_key,category,osm_type,osm_id,wikidata,dedup_reason "
                "FROM spatial.osm_destination_candidates WHERE source_file_id=:id "
                "ORDER BY candidate_key"
            ), {"id": src["source_file_id"]}).mappings()]
            snaps = [dict(row) for row in conn.execute(text(
                "SELECT network_id,destination_kind,destination_key,category "
                "FROM spatial.walking_destination_snaps ORDER BY destination_kind,destination_key"
            )).mappings()]
            euclidean = [dict(row) for row in conn.execute(text(
                "SELECT source_file_id,taxonomy_version,count(*) AS n "
                "FROM features.euclidean_accessibility GROUP BY 1,2"
            )).mappings()]
            walking = [dict(row) for row in conn.execute(text(
                "SELECT w.network_id,n.source_file_id,count(*) AS n "
                "FROM features.walking_accessibility w "
                "JOIN spatial.walking_networks n USING(network_id) GROUP BY 1,2"
            )).mappings()]
            conn.rollback()
    finally:
        engine.dispose()
    return canonical, {"source": src, "candidates": candidates, "snaps": snaps,
                       "euclidean": euclidean, "walking": walking}


def subtype(row: dict) -> str:
    """One exclusive display subtype; retain all original tags in the database."""
    tags = row["tags"]
    if row["destination_group"] == "food_social":
        value = tags.get("amenity")
        if value not in FOOD_AMENITIES:
            raise ValueError("Food canonical row has no frozen qualifying amenity")
        return value
    if row["destination_group"] == "cultural_tourist":
        # Multi-tag destinations appear once. Precedence is fixed for reporting,
        # not a revision of the Phase 5 inclusion OR rule.
        for key, allowed in (("tourism", CULTURE_TOURISM), ("amenity", CULTURE_AMENITIES),
                             ("historic", CULTURE_HISTORIC)):
            if tags.get(key) in allowed:
                return tags[key]
        raise ValueError("Cultural canonical row has no frozen qualifying tag")
    if tags.get("railway") in STATION_RAILWAY:
        return tags["railway"]
    return "public_transport_station"


def qualifying_tags(row: dict) -> str:
    tags = row["tags"]
    group = row["destination_group"]
    if group == "food_social":
        keys = (("amenity", FOOD_AMENITIES),)
    elif group == "cultural_tourist":
        keys = (("tourism", CULTURE_TOURISM), ("amenity", CULTURE_AMENITIES),
                ("historic", CULTURE_HISTORIC))
    else:
        keys = (("railway", STATION_RAILWAY), ("public_transport", {"station"}),
                ("train", {"yes"}), ("subway", {"yes"}),
                ("station", {"subway", "light_rail", "train"}))
    return json.dumps([f"{key}={tags[key]}" for key, allowed in keys if tags.get(key) in allowed],
                      ensure_ascii=False)


def validate(canonical: list[dict], meta: dict) -> dict[str, int]:
    src = meta["source"]
    keys = [r["canonical_id"] for r in canonical]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate canonical destination key")
    counts = Counter(r["destination_group"] for r in canonical)
    if counts != {"food_social": 3006, "cultural_tourist": 463, "station": 143}:
        raise ValueError(f"Canonical counts differ from frozen Phase 5 report: {counts}")
    with (ROOT / "outputs/tables/phase05/destination_counts.csv").open(newline="", encoding="utf-8") as stream:
        saved = {r["category"]: int(r["canonical_n"]) for r in csv.DictReader(stream)}
    if dict(counts) != saved:
        raise ValueError(f"Canonical counts differ from saved Phase 5 count CSV: {saved}")
    source_file = ROOT / src["relative_path"]
    if not source_file.is_file():
        raise FileNotFoundError(f"Frozen OSM source archive unavailable for hash check: {source_file}")
    with source_file.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != src["file_hash_sha256"]:
            raise ValueError("Frozen OSM source archive hash differs from meta.source_files")
    if any(r["source_file_id"] != src["source_file_id"] or
           r["taxonomy_version"] != TAXONOMY_VERSION or
           r["srid_wgs84"] != 4326 or r["srid_metric"] != 25832 for r in canonical):
        raise ValueError("Source/taxonomy/CRS mismatch in canonical tables")
    if any(categories(r["tags"]).count(r["destination_group"]) != 1 for r in canonical):
        raise ValueError("Canonical tag no longer satisfies frozen Phase 5 taxonomy")
    if any(r["destination_group"] == "station" and station_mode(r["tags"]) != r["mode"]
           for r in canonical):
        raise ValueError("Station mode does not match frozen classification")
    if Counter(r["mode"] for r in canonical if r["kind"] == "station") != \
            {"metro": 37, "urban_rail": 101, "rail": 5}:
        raise ValueError("Station mode counts differ from the Phase 5 report/map legend")
    if any(bool(r["inside_study_union"]) != bool(r["study_municipality"]) for r in canonical):
        raise ValueError("Union and municipality assignment disagree")

    linked: dict[str, list[dict]] = defaultdict(list)
    for candidate in meta["candidates"]:
        linked[candidate["canonical_candidate_key"]].append(candidate)
    if set(linked) != set(keys) or len(meta["candidates"]) != 3643:
        raise ValueError("Canonical/candidate link set differs from Phase 5")
    for row in canonical:
        group = linked[row["canonical_id"]]
        expected = {(c["osm_type"], c["osm_id"]) for c in group}
        recorded = {(ref["osm_type"], ref["osm_id"]) for ref in row["merged_osm_refs"]}
        if (len(expected) != len(group) or expected != recorded or
                row["duplicate_count"] != len(group)-1 or
                not any(c["candidate_key"] == row["canonical_id"] and
                        c["dedup_reason"] == "canonical" for c in group)):
            raise ValueError(f"Dedup provenance mismatch: {row['canonical_id']}")
        row["deduplication_provenance"] = json.dumps(
            dict(sorted(Counter(c["dedup_reason"] for c in group).items())),
            sort_keys=True, ensure_ascii=False)
        row["wikidata_ids"] = ";".join(sorted({c["wikidata"] for c in group if c["wikidata"]}))
        row["osm_subtype"] = subtype(row)
        row["all_qualifying_osm_tags"] = qualifying_tags(row)
    if len(meta["euclidean"]) != 1 or meta["euclidean"][0]["source_file_id"] != src["source_file_id"] \
            or meta["euclidean"][0]["taxonomy_version"] != TAXONOMY_VERSION:
        raise ValueError("Euclidean features do not reference the canonical source/version")
    snap_keys = {(s["destination_kind"], s["destination_key"], s["category"]) for s in meta["snaps"]}
    canonical_keys = {(r["kind"], r["canonical_id"], r["destination_group"]) for r in canonical}
    if len(meta["snaps"]) != len(snap_keys) or len({s["network_id"] for s in meta["snaps"]}) != 1 \
            or snap_keys != canonical_keys:
        raise ValueError("Walking snaps are not exactly the Phase 5 canonical destination universe")
    if len(meta["walking"]) != 1 or meta["walking"][0]["source_file_id"] != src["source_file_id"] \
            or meta["walking"][0]["network_id"] != meta["snaps"][0]["network_id"]:
        raise ValueError("Walking features do not reference the snapped Phase 5 source/network")
    return counts


def source_label(src: dict) -> str:
    return f"{src['filename']} ({src['source_date'].isoformat()}; SHA-256 {src['file_hash_sha256']})"


def inventory_row(row: dict, src: dict, *, station: bool = False) -> dict:
    base = {
        "canonical_destination_id": row["canonical_id"],
        "canonical_name": row["name"] or "",  # NULL remains unnamed, never invented.
        "destination_group": row["destination_group"],
        "osm_subtype": row["osm_subtype"],
        "all_qualifying_osm_tags": row["all_qualifying_osm_tags"],
        "osm_element_type": row["osm_type"],
        "preferred_osm_id": row["osm_id"],
        "all_source_osm_refs": json.dumps(row["merged_osm_refs"], ensure_ascii=False, sort_keys=True),
        "wikidata_id": row["wikidata_ids"],
        "longitude": row["longitude"], "latitude": row["latitude"],
        "inside_study_union": bool(row["inside_study_union"]),
        "source_version": source_label(src),
        "taxonomy_version": row["taxonomy_version"],
        "deduplication_provenance": row["deduplication_provenance"],
    }
    if station:
        return {
            "canonical_station_id": base.pop("canonical_destination_id"),
            "station_name": base.pop("canonical_name"),
            "mode": row["mode"], **base,
            "municipality_or_external_status": row["study_municipality"] or
            "Outside Copenhagen–Frederiksberg study union",
        }
    return base


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_md(path: Path, heading: str, note: str, rows: list[dict], columns: list[str]) -> None:
    # Escape only Markdown cell delimiters; CSV remains lossless for source names.
    cell = lambda value: str(value if value is not None else "").replace("|", r"\|").replace("\n", " ")
    lines = [f"# {heading}", "", note, "", "| " + " | ".join(columns) + " |",
             "| " + " | ".join(["---"] * len(columns)) + " |"]
    lines.extend("| " + " | ".join(cell(row.get(col, "")) for col in columns) + " |" for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def taxonomy_rows() -> list[dict]:
    rows = []
    for name in FOOD_ORDER:
        rows.append({"Destination group": "food_social", "OSM subtype / tag concept": f"amenity={name}",
                     "Included?": "Yes", "Important rule": "Exact amenity tag; canonical deduplicated point",
                     "Primary use": "Food/social 800 m Euclidean and 10 min walking counts",
                     "Notes": "Takeaway-only and fast-food-only tags do not qualify"})
    for name in CULTURE_ORDER:
        tag = "tourism" if name in CULTURE_TOURISM else "amenity" if name == "theatre" else "historic"
        rows.append({"Destination group": "cultural_tourist", "OSM subtype / tag concept": f"{tag}={name}",
                     "Included?": "Yes", "Important rule": "Any qualifying tourism/amenity/historic tag; canonical point",
                     "Primary use": "Culture/tourism 800 m Euclidean and 10 min walking counts",
                     "Notes": "Display subtype uses tourism, then amenity, then historic precedence if multi-tagged"})
    rows.extend([
        {"Destination group": "cultural_tourist", "OSM subtype / tag concept": "historic=memorial only",
         "Included?": "No", "Important rule": "Memorial-only objects excluded in phase05_v2",
         "Primary use": "None", "Notes": "May remain in raw audit extract; not a canonical destination"},
        {"Destination group": "station", "OSM subtype / tag concept": "railway=station or railway=halt",
         "Included?": "Yes, if named", "Important rule": "Name required; mode classified from subway/station/network tags",
         "Primary use": "Nearest rail/metro station, Euclidean distance and walking minutes",
         "Notes": "Modes: metro, urban_rail, rail"},
        {"Destination group": "station", "OSM subtype / tag concept": "public_transport=station plus train=yes, subway=yes, or station=subway/light_rail/train",
         "Included?": "Yes, if named", "Important rule": "Rail/subway qualifier and name required",
         "Primary use": "Same nearest-station set", "Notes": "Included by OR rule even without railway tag"},
        {"Destination group": "station", "OSM subtype / tag concept": "bus/tram-only stop or subway entrance",
         "Included?": "No", "Important rule": "Not a named qualifying station entity",
         "Primary use": "None in primary rail-station measure", "Notes": "Bus proximity is a separate robustness measure"},
        {"Destination group": "all", "OSM subtype / tag concept": "source and deduplication",
         "Included?": "Rule-dependent", "Important rule": "Node preferred over way then relation; same-name/Wikidata proximity merges within category",
         "Primary use": "Same canonical endpoint IDs for Euclidean and walking features",
         "Notes": "No price/outcome information enters the taxonomy or deduplication"},
    ])
    return rows


def count_rows(canonical: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    for row in canonical:
        key = row["destination_group"], row["osm_subtype"], row["mode"] or "not applicable"
        grouped[key]["inside" if row["inside_study_union"] else "outside"] += 1
    for group, subtypes in (("food_social", FOOD_ORDER), ("cultural_tourist", CULTURE_ORDER)):
        for subtype_name in subtypes:
            grouped[(group, subtype_name, "not applicable")]  # show zero-count included tags
    rows = []
    for (group, sub, mode), tally in sorted(grouped.items()):
        inside, outside = tally["inside"], tally["outside"]
        rows.append({"destination_group": group, "OSM subtype": sub, "transport mode": mode,
                     "inside Copenhagen–Frederiksberg study union": inside,
                     "outside Copenhagen–Frederiksberg study union": outside,
                     "total": inside + outside})
    for group in GROUPS:
        inside = sum(bool(r["inside_study_union"]) for r in canonical if r["destination_group"] == group)
        total = sum(r["destination_group"] == group for r in canonical)
        rows.append({"destination_group": group, "OSM subtype": "ALL SUBTYPES",
                     "transport mode": "all modes" if group == "station" else "not applicable",
                     "inside Copenhagen–Frederiksberg study union": inside,
                     "outside Copenhagen–Frederiksberg study union": total-inside,
                     "total": total})
    return rows


def examples(canonical: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in canonical:
        if row["kind"] == "poi" and row["name"]:
            grouped[(row["destination_group"], row["osm_subtype"])].append(row)
    result = []
    for group in ("food_social", "cultural_tourist"):
        for sub in (FOOD_ORDER if group == "food_social" else CULTURE_ORDER):
            for row in sorted(grouped[(group, sub)], key=lambda r: (r["name"].casefold(), r["canonical_id"]))[:3]:
                result.append({"Destination group": group, "OSM subtype": sub,
                               "Canonical name": row["name"], "Canonical destination ID": row["canonical_id"],
                               "Preferred OSM ref": f"{row['osm_type']}/{row['osm_id']}",
                               "Inside study union": bool(row["inside_study_union"])})
    return result


def export_latex(taxonomy: list[dict], counts: list[dict], ex: list[dict], stations: list[dict]) -> None:
    # Thesis-facing tables only. Thousands of POIs remain in supplementary CSV.
    save(LATEX / "destination_taxonomy.tex", longtable(
        "Frozen OpenStreetMap destination taxonomy", "tab:destination-taxonomy",
        ["Group", "OSM tag concept", "Included?", "Rule", "Primary use"],
        [line([tex(r[k]) for k in ("Destination group", "OSM subtype / tag concept", "Included?",
                                   "Important rule", "Primary use")]) for r in taxonomy],
        "p{2.3cm}p{5.1cm}p{2.0cm}p{6.0cm}p{5.2cm}",
        "Frozen phase05\\_v2, before price modelling. Memorial-only, bus/tram-only and entrance objects are excluded as stated; food/culture counts and nearest station use these canonical endpoints."))
    save(LATEX / "destination_counts.tex", longtable(
        "Canonical destinations by subtype, mode and study-union position", "tab:destination-counts",
        ["Group", "Subtype", "Mode", "Inside", "Outside", "Total"],
        [line([tex(r["destination_group"]), tex(r["OSM subtype"]), tex(r["transport mode"]),
               num(r["inside Copenhagen–Frederiksberg study union"], count=True),
               num(r["outside Copenhagen–Frederiksberg study union"], count=True),
               num(r["total"], count=True)]) for r in counts],
        "p{3.3cm}p{5.3cm}p{2.7cm}rrr",
        "Post-deduplication Phase 5 counts, not raw OSM elements. Inside means ST\\_Covers by the official two-municipality union in EPSG:25832. Included multi-tagged cultural objects receive one display subtype, prioritising tourism, then amenity, then historic; ALL SUBTYPES rows are group totals. The primary accessibility universe includes outside endpoints."))
    save(LATEX / "destination_examples.tex", longtable(
        "Deterministic examples of canonical food and cultural destinations", "tab:destination-examples",
        ["Group", "Subtype", "Canonical name", "Preferred OSM ref", "Inside?"],
        [line([tex(r["Destination group"]), tex(r["OSM subtype"]), tex(r["Canonical name"]),
               tex(r["Preferred OSM ref"]), "Yes" if r["Inside study union"] else "No"]) for r in ex],
        "p{3.0cm}p{2.7cm}p{9.0cm}p{3.7cm}p{1.6cm}",
        "First three named canonical destinations per displayed subtype, sorted by Unicode casefolded name then canonical ID. Illustrative only: this is neither a random sample nor selected by listing price, model fit or accessibility. Full POI inventories are supplementary CSVs."))
    save(LATEX / "destination_rail_metro_full.tex", longtable(
        "Complete canonical rail, metro and urban-rail station inventory", "tab:destination-stations",
        ["Station name", "Mode", "OSM ref", "Inside?", "Study municipality/status"],
        [line([tex(r["station_name"]), tex(r["mode"]),
               tex(f"{r['osm_element_type']}/{r['preferred_osm_id']}"),
               "Yes" if r["inside_study_union"] else "No",
               tex(r["municipality_or_external_status"])]) for r in stations],
        "p{8.0cm}p{2.4cm}p{3.7cm}p{1.5cm}p{5.2cm}",
        "All 143 post-deduplication Phase 5 station entities are shown. The same station keys define straight-line and walking nearest-station measures. Outside endpoints remain in the primary buffered destination universe. Full IDs, coordinates, merged OSM refs and source provenance are in the supplementary rail CSV."))


def main() -> None:
    canonical, meta = read_database()
    group_counts = validate(canonical, meta)
    src = meta["source"]
    taxonomy, counts, ex = taxonomy_rows(), count_rows(canonical), examples(canonical)
    food = [inventory_row(r, src) for r in canonical if r["destination_group"] == "food_social"]
    culture = [inventory_row(r, src) for r in canonical if r["destination_group"] == "cultural_tourist"]
    stations = [inventory_row(r, src, station=True) for r in canonical if r["kind"] == "station"]
    station_columns = ["canonical_station_id", "station_name", "mode", *REF_COLUMNS[2:],
                       "municipality_or_external_status"]
    write_csv(SUPPLEMENT / "destination_inventory_food_social.csv", food, list(REF_COLUMNS))
    write_csv(SUPPLEMENT / "destination_inventory_cultural_tourist.csv", culture, list(REF_COLUMNS))
    write_csv(SUPPLEMENT / "destination_inventory_rail_metro.csv", stations, station_columns)
    write_csv(FINAL / "appendix_destination_rail_metro.csv", stations, station_columns)
    tax_columns = list(taxonomy[0])
    count_columns = list(counts[0])
    ex_columns = list(ex[0])
    write_csv(FINAL / "appendix_destination_taxonomy.csv", taxonomy, tax_columns)
    write_csv(FINAL / "appendix_destination_counts.csv", counts, count_columns)
    write_csv(FINAL / "appendix_destination_examples.csv", ex, ex_columns)
    write_md(FINAL / "appendix_destination_taxonomy.md", "Frozen Phase 5 destination taxonomy",
             "Version phase05_v2. Rules were set before price modelling; the source OSM snapshot is 2026-09-26. See the full supplementary inventories for all canonical IDs and coordinates.",
             taxonomy, tax_columns)
    write_md(FINAL / "appendix_destination_counts.md", "Canonical OSM destination counts",
             "Post-deduplication counts from the live Phase 5 canonical PostGIS tables. Inside/outside is ST_Covers against the official Copenhagen–Frederiksberg union in EPSG:25832. Primary accessibility retains outside endpoints. Subtypes are exclusive display labels (tourism > amenity > historic for multi-tagged cultural objects); group totals should not be added to subtype rows.",
             counts, count_columns)
    write_md(FINAL / "appendix_destination_examples.md", "Illustrative canonical destination examples",
             "First three named rows per POI display subtype, ordered by casefolded canonical name then canonical ID. No listing data, price or model information affects selection. An unrepresented subtype has no named canonical row and is not fabricated.",
             ex, ex_columns)
    compact_stations = [{"Canonical station ID": r["canonical_station_id"], "Station name": r["station_name"],
                         "Mode": r["mode"], "OSM subtype": r["osm_subtype"],
                         "Preferred OSM ref": f"{r['osm_element_type']}/{r['preferred_osm_id']}",
                         "Inside study union": r["inside_study_union"],
                         "Municipality / external status": r["municipality_or_external_status"]}
                        for r in stations]
    write_md(FINAL / "appendix_destination_rail_metro.md", "Complete canonical station inventory",
             "All 143 canonical rail/metro/urban-rail station entities are listed. Full OSM refs, Wikidata, public coordinates and provenance remain in the companion CSV. Bus/tram-only stops are excluded from this primary station set.",
             compact_stations, list(compact_stations[0]))
    export_latex(taxonomy, counts, ex, stations)

    inside = Counter(r["destination_group"] for r in canonical if r["inside_study_union"])
    modes = Counter(r["mode"] for r in canonical if r["kind"] == "station")
    refs = Counter(c["dedup_reason"] for c in meta["candidates"])
    lines = [
        "# Frozen Phase 5 OSM destination inventory for thesis appendix", "",
        "This is a read-only documentation export from the canonical PostGIS tables, not a new extraction or feature construction. No price/model data were accessed.", "",
        "Reproduce on the existing thesis database with `make destination-inventory` (or run `.venv/bin/python -m src.pipeline.export_destination_inventory_appendix` and then `.venv/bin/python -m src.pipeline.export_final_latex_tables`). The exporter fails if the archived PBF hash, saved Phase 5 counts, or Phase 6 snapped canonical keys differ.", "",
        f"- Taxonomy: `{TAXONOMY_VERSION}`; OSM source: `{src['filename']}`, dated {src['source_date']} and acquired {src['acquisition_date']}; SHA-256 `{src['file_hash_sha256']}`.",
        f"- Archived source URL: {src['source_url'] or 'not recorded'}; recorded source extent: {src['geographic_extent'] or 'not recorded'}.",
        "- The OSM map state is roughly three months later than the 2026-06-30 Airbnb listing snapshot. OSM does not exhaustively represent real-world destinations.",
        "- Source geometry is EPSG:4326; spatial inside/outside classification uses ST_Covers with the official two-municipality union in EPSG:25832. The buffered primary accessibility universe is **not** clipped to that union.",
        "", "## Exact post-deduplication counts", "",
        "| Group | Inside study union | Outside study union | Total |", "| --- | ---: | ---: | ---: |",
    ]
    for group in GROUPS:
        lines.append(f"| {group} | {inside[group]:,} | {group_counts[group]-inside[group]:,} | {group_counts[group]:,} |")
    lines.extend(["", f"Station modes: metro {modes['metro']}, urban_rail {modes['urban_rail']}, rail {modes['rail']}. "
                  "The 143 stations are named railway stations/halts or named qualifying public-transport stations. "
                  "Bus/tram-only stops and subway entrances are not primary stations.",
                  "", "## Taxonomy and deduplication", "",
                  "Food/social = amenity restaurant/cafe/bar/pub. Cultural/tourist = tourism museum/gallery/attraction/viewpoint, amenity theatre, or historic monument/castle/palace. Memorial-only historical objects were excluded in phase05_v2 before price modelling. Other nonqualifying fast-food/takeaway-only, accommodation, generic historic and unnamed station tags remain excluded. A multi-tag object can qualify in more than one destination group; within a group it appears once. The subtype summary assigns one mutually exclusive display subtype, prioritising tourism, then amenity, then historic for multi-tag cultural POIs; this changes no inclusion rule. The full inventories retain an `all_qualifying_osm_tags` JSON field, so a palace-tagged attraction is still identifiable even when its exclusive display subtype is attraction.",
                  f"Candidate-link audit: {len(meta['candidates']):,} Phase 5 candidates map to {len(canonical):,} canonical rows; dedup reasons are canonical {refs['canonical']}, same-name-nearby {refs['same_name_nearby']}, same-Wikidata-nearby {refs['same_wikidata_nearby']}. Every canonical row has exactly the stored merged OSM refs and duplicate count. Nodes were preferred to ways, then relations, then lower OSM ID under the frozen within-category distance rules. Wikidata IDs in the CSV are drawn from all merged candidates where available; multiple distinct IDs, if any, are semicolon-separated.",
                  "", "## Appendix and supplementary files", "",
                  "- Appendix CSV/Markdown: `outputs/tables/final/appendix_destination_taxonomy.*`, `appendix_destination_counts.*`, `appendix_destination_examples.*`, and `appendix_destination_rail_metro.*`.",
                  "- Appendix LaTeX: `outputs/latex/appendix/destination_taxonomy.tex`, `destination_counts.tex`, `destination_examples.tex`, and `destination_rail_metro_full.tex`.",
                  "- Full supplementary CSVs: `outputs/tables/supplementary/destination_inventory_food_social.csv`, `destination_inventory_cultural_tourist.csv`, and `destination_inventory_rail_metro.csv`. They contain only public OSM destination coordinates/IDs, never Airbnb listing coordinates or IDs.",
                  "", "## Reconciliation and manuscript note", "",
                  f"The exported group totals match the saved `outputs/tables/phase05/destination_counts.csv`: {group_counts['food_social']:,} food/social, {group_counts['cultural_tourist']:,} cultural/tourist and {group_counts['station']:,} stations. "
                  f"All {len(canonical):,} canonical keys appear exactly once in Phase 6 `spatial.walking_destination_snaps` on network `{meta['snaps'][0]['network_id']}`. "
                  f"The Euclidean feature table has {meta['euclidean'][0]['n']:,} rows with this Phase 5 source/version; the walking feature table has {meta['walking'][0]['n']:,} rows on the same source/network. "
                  "Station modes agree with the Phase 5 report and Phase 8 map legend. No raw OSM duplicate was separately exported after canonical merging.",
                  "", "**Manuscript-ready appendix note.** Accessibility measures use a fixed canonical OSM destination universe. Euclidean and walking measures use the same destinations: raw OSM elements were deduplicated before feature construction, and the taxonomy was fixed before price modelling. Memorial-only objects were excluded from the cultural/tourist set; bus stops are not part of the primary rail/metro/S-train station set. Full canonical inventories are supplied as supplementary machine-readable files. The OSM snapshot is dated 26 September 2026, roughly three months after the 30 June 2026 Airbnb snapshot. OSM mapping is not exhaustive of real-world destinations.",
                  "", "**Freeze:** no destination definition changed; no accessibility feature changed; no model was refitted. This export documents the existing frozen destination universe.", ""])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Exported {len(canonical)} canonical destinations ({dict(group_counts)}); source {src['filename']} {src['source_date']}")


if __name__ == "__main__":
    main()
