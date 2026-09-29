"""Load official boundaries, assign spatial IDs, and export aggregate Phase 4 geography."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy import text

from src.db.sources import prepare_source, register_records
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.output_paths import PhaseDirectory
from src.pipeline.run_spatial_phase4 import EXTRACTION_BUFFER_METRES, SNAPSHOT


def archive_directory() -> Path:
    candidates = sorted((PROJECT_ROOT / "data/raw/official_boundaries").glob("*/acquisition_metadata.json"))
    if not candidates:
        raise FileNotFoundError("Run `make phase4-acquire-boundaries` to archive official boundaries")
    return candidates[-1].parent


def import_official_boundaries(engine) -> dict[str, int]:
    directory = archive_directory()
    files = {
        "copenhagen_municipality.geojson": "spatial.official_municipalities",
        "frederiksberg_municipality.geojson": "spatial.official_municipalities",
        "copenhagen_districts.geojson": "spatial.official_copenhagen_districts",
    }
    records = [prepare_source(directory / name) for name in files]
    ids = dict(zip(files, register_records(engine, records)))
    register_records(engine, [prepare_source(directory / "acquisition_metadata.json")])
    for name, table in files.items():
        path = directory / name
        data = json.loads(path.read_text(encoding="utf-8"))
        features = data["features"] if name == "copenhagen_districts.geojson" else [data]
        with engine.connect() as conn:
            already = conn.scalar(text(
                "SELECT count(*) FROM meta.import_runs WHERE source_file_id=:id "
                "AND target_table=:table AND status='success'"
            ), {"id": ids[name], "table": table})
        if already:
            continue
        with engine.begin() as conn:
            run_id = conn.scalar(text(
                "INSERT INTO meta.import_runs (source_file_id,source_hash_sha256,target_table,import_options,status) "
                "VALUES (:id,:hash,:table,CAST(:options AS jsonb),'running') RETURNING import_run_id"
            ), {"id": ids[name], "hash": next(r["file_hash_sha256"] for r in records if r["filename"] == name),
                "table": table, "options": json.dumps({"source_crs": 4326, "metric_crs": 25832})})
        try:
            with engine.begin() as conn:
                for feature in features:
                    props = feature["properties"]
                    geometry = json.dumps(feature["geometry"], separators=(",", ":"))
                    valid = conn.execute(text(
                        "WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326) AS geom) "
                        "SELECT ST_IsValid(geom),NOT ST_IsEmpty(geom),ST_XMin(geom)>12.2 "
                        "AND ST_XMax(geom)<13 AND ST_YMin(geom)>55.4 AND ST_YMax(geom)<56 "
                        "FROM g"
                    ), {"geometry": geometry}).one()
                    if tuple(valid) != (True, True, True):
                        raise ValueError(f"Invalid/out-of-area official geometry in {name}")
                    if name == "copenhagen_districts.geojson":
                        conn.execute(text(
                            "WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326) AS geom), "
                            "p AS (SELECT geom,ST_Transform(geom,25832) AS metric FROM g) "
                            "INSERT INTO spatial.official_copenhagen_districts "
                            "(district_number,district_name,source_file_id,source_crs_epsg,geom_source,geom_4326,geom_25832,boundary_25832) "
                            "SELECT :number,:name,:source_id,4326,geom,geom,metric,ST_Boundary(metric) FROM p"
                        ), {"geometry": geometry, "number": props["bydel_nr"], "name": props["navn"], "source_id": ids[name]})
                    else:
                        conn.execute(text(
                            "WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326) AS geom), "
                            "p AS (SELECT geom,ST_Transform(geom,25832) AS metric FROM g) "
                            "INSERT INTO spatial.official_municipalities "
                            "(municipality_code,municipality_name,source_file_id,source_crs_epsg,source_geo_changed_at,"
                            "geom_source,geom_4326,geom_25832,boundary_25832) "
                            "SELECT :code,:name,:source_id,4326,:changed,geom,geom,metric,ST_Boundary(metric) FROM p"
                        ), {"geometry": geometry, "code": props["kode"], "name": props["navn"],
                            "source_id": ids[name], "changed": props.get("geo_ændret")})
                conn.execute(text(
                    "UPDATE meta.source_files SET imported_at=now(),row_count=:rows WHERE source_file_id=:id"
                ), {"rows": len(features), "id": ids[name]})
                conn.execute(text(
                    "UPDATE meta.import_runs SET status='success',finished_at=now(),rows_loaded=:rows "
                    "WHERE import_run_id=:run_id"
                ), {"rows": len(features), "run_id": run_id})
        except Exception as error:
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE meta.import_runs SET status='failed',finished_at=now(),error_message=:message "
                    "WHERE import_run_id=:run_id"
                ), {"run_id": run_id, "message": type(error).__name__})
            raise
    return ids


def import_map_context_boundaries(engine) -> int:
    candidates = sorted((PROJECT_ROOT / "data/raw/official_map_context").glob("*/acquisition_metadata.json"))
    if not candidates:
        raise FileNotFoundError("Run `make phase4-acquire-map-context` to archive surrounding municipalities")
    directory = candidates[-1].parent
    path = directory / "capital_region_municipalities.geojson"
    record = prepare_source(path)
    source_id = register_records(engine, [record])[0]
    register_records(engine, [prepare_source(directory / "acquisition_metadata.json")])
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features", [])
    if data.get("type") != "FeatureCollection" or len(features) < 20:
        raise ValueError("Unexpected archived official map-context source")
    with engine.connect() as conn:
        prior = conn.scalar(text(
            "SELECT count(*) FROM meta.import_runs WHERE source_file_id=:id "
            "AND target_table='spatial.map_context_municipalities' AND status='success'"
        ), {"id": source_id})
        if prior:
            existing = conn.execute(text(
                "SELECT count(*) AS n,count(*) FILTER (WHERE source_file_id<>:id) AS wrong_source "
                "FROM spatial.map_context_municipalities"
            ), {"id": source_id}).one()
            if tuple(existing) != (len(features), 0):
                raise RuntimeError("Previously imported context municipalities differ from logged source")
            return source_id
    with engine.begin() as conn:
        run_id = conn.scalar(text(
            "INSERT INTO meta.import_runs (source_file_id,source_hash_sha256,target_table,import_options,status) "
            "VALUES (:id,:hash,'spatial.map_context_municipalities',CAST(:options AS jsonb),'running') "
            "RETURNING import_run_id"
        ), {"id": source_id, "hash": record["file_hash_sha256"],
            "options": json.dumps({"source_crs": 4326, "metric_crs": 25832,
                                   "purpose": "cartographic context only"})})
    try:
        with engine.begin() as conn:
            if conn.scalar(text("SELECT count(*) FROM spatial.map_context_municipalities")):
                raise RuntimeError("Context municipality table already contains a different source")
            for feature in features:
                props = feature["properties"]
                if (props.get("udenforkommuneinddeling") or
                        feature.get("geometry", {}).get("type") != "MultiPolygon"):
                    raise ValueError("Unexpected non-municipal or non-polygon context feature")
                geometry = json.dumps(feature["geometry"], separators=(",", ":"))
                valid = conn.execute(text(
                    "WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326) AS geom) "
                    "SELECT ST_IsValid(geom),NOT ST_IsEmpty(geom),"
                    "ST_XMin(geom)>7 AND ST_XMax(geom)<16 AND ST_YMin(geom)>54 AND ST_YMax(geom)<59 FROM g"
                ), {"geometry": geometry}).one()
                if tuple(valid) != (True, True, True):
                    raise ValueError(f"Invalid context municipality geometry: {props.get('kode')}")
                conn.execute(text(
                    "WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326) AS geom) "
                    "INSERT INTO spatial.map_context_municipalities "
                    "(municipality_code,municipality_name,source_file_id,source_crs_epsg,geom_source,geom_4326,geom_25832) "
                    "SELECT :code,:name,:source_id,4326,geom,geom,ST_Transform(geom,25832) FROM g"
                ), {"geometry": geometry, "code": props["kode"], "name": props["navn"],
                    "source_id": source_id})
            conn.execute(text("UPDATE meta.source_files SET imported_at=now(),row_count=:rows WHERE source_file_id=:id"),
                         {"rows": len(features), "id": source_id})
            conn.execute(text(
                "UPDATE meta.import_runs SET status='success',finished_at=now(),rows_loaded=:rows "
                "WHERE import_run_id=:run_id"
            ), {"rows": len(features), "run_id": run_id})
    except Exception as error:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE meta.import_runs SET status='failed',finished_at=now(),error_message=:message "
                "WHERE import_run_id=:run_id"
            ), {"run_id": run_id, "message": type(error).__name__})
        raise
    return source_id


def assign_official_geography(engine, ids: dict[str, int]) -> dict:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM spatial.study_area WHERE area_kind='official_study_area'"))
        conn.execute(text(
            "WITH g AS (SELECT ST_Multi(ST_UnaryUnion(ST_Collect(geom_25832))) AS geom "
            "FROM spatial.official_municipalities) "
            "INSERT INTO spatial.study_area (area_kind,description,source_file_id,buffer_metres,geom_4326,geom_25832) "
            "SELECT 'official_study_area','Union of official Copenhagen and Frederiksberg municipality boundaries',"
            "NULL,0,ST_Transform(geom,4326),geom FROM g"
        ))
        conn.execute(text(
            "WITH p AS (SELECT geom_25832 AS geom FROM spatial.study_area WHERE area_kind='official_study_area'), "
            "l AS (SELECT ST_Collect(geom_25832) AS geom FROM clean.airbnb_listings "
            "WHERE snapshot_date=:snapshot AND valid_coordinates), "
            "g AS (SELECT ST_Multi(ST_Buffer(ST_UnaryUnion(ST_Collect(p.geom,l.geom)),:buffer)) AS geom FROM p,l) "
            "UPDATE spatial.study_area s SET description='Union of official municipalities and valid listing points, "
            "buffered 1500 m in EPSG:25832',source_file_id=NULL,geom_25832=g.geom,"
            "geom_4326=ST_Transform(g.geom,4326) FROM g WHERE s.area_kind='planned_15min_extraction'"
        ), {"snapshot": SNAPSHOT, "buffer": EXTRACTION_BUFFER_METRES})
        conn.execute(text(
            "WITH matched AS (SELECT l.snapshot_date,l.listing_id, "
            "count(DISTINCT m.municipality_code)::integer AS municipality_matches, "
            "min(m.municipality_code) AS municipality_code, "
            "count(DISTINCT a.area_id)::integer AS area_matches,min(a.area_id) AS area_id,"
            "min(a.municipality_code) AS area_municipality_code "
            "FROM clean.airbnb_listings l "
            "LEFT JOIN spatial.official_municipalities m ON ST_Covers(m.geom_4326,l.geom) "
            "LEFT JOIN spatial.official_cv_areas a ON ST_Covers(a.geom_4326,l.geom) "
            "WHERE l.snapshot_date=:snapshot GROUP BY l.snapshot_date,l.listing_id) "
            "UPDATE features.listing_spatial_base s SET "
            "official_municipality_match_count=x.municipality_matches,"
            "official_municipality_code=CASE WHEN x.municipality_matches=1 THEN x.municipality_code END,"
            "official_cv_match_count=x.area_matches,"
            "official_cv_area_id=CASE WHEN x.municipality_matches=1 AND x.area_matches=1 "
            "AND x.municipality_code=x.area_municipality_code THEN x.area_id END,"
            "official_assignment_status=CASE WHEN x.municipality_matches=1 AND x.area_matches=1 "
            "AND x.municipality_code=x.area_municipality_code "
            "THEN 'unique_official_area' WHEN x.municipality_matches=0 OR x.area_matches=0 "
            "THEN 'outside_or_gap' WHEN x.municipality_code<>x.area_municipality_code "
            "THEN 'municipality_district_conflict' ELSE 'multiple_official_areas' END,"
            "context_statistical_unit_id=NULL,"
            "context_assignment_status='official_polygon_loaded_context_crosswalk_pending',"
            "near_official_border_100m=EXISTS (SELECT 1 FROM spatial.official_cv_areas b "
            "WHERE ST_DWithin(l.geom_25832,b.boundary_25832,100)) "
            "FROM matched x JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
            "WHERE s.snapshot_date=x.snapshot_date AND s.listing_id=x.listing_id"
        ), {"snapshot": SNAPSHOT})
        qa = dict(conn.execute(text(
            "SELECT count(*) AS n,count(*) FILTER (WHERE official_municipality_match_count=0) AS no_municipality,"
            "count(*) FILTER (WHERE official_municipality_match_count>1) AS multiple_municipalities,"
            "count(*) FILTER (WHERE official_cv_match_count=0) AS no_cv_area,"
            "count(*) FILTER (WHERE official_cv_match_count>1) AS multiple_cv_areas,"
            "count(*) FILTER (WHERE near_official_border_100m) AS near_border_100m,"
            "count(*) FILTER (WHERE primary_sample_candidate AND official_cv_area_id IS NULL) AS primary_unassigned "
            "FROM features.listing_spatial_base s JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
            "WHERE s.snapshot_date=:snapshot"
        ), {"snapshot": SNAPSHOT}).mappings().one())
        coverage = dict(conn.execute(text(
            "SELECT ST_Area(p.geom_25832)/1000000.0 AS planned_footprint_km2,"
            "ST_Area(ST_Intersection(o.geom_25832,p.geom_25832))/ST_Area(p.geom_25832) "
            "AS archived_osm_overlap_fraction,ST_Covers(o.geom_25832,p.geom_25832) "
            "AS archived_osm_covers_planned "
            "FROM spatial.study_area o CROSS JOIN spatial.study_area p "
            "WHERE o.area_kind='archived_osm_bbox' AND p.area_kind='planned_15min_extraction'"
        )).mappings().one())
    return {**qa, **coverage}


def export_official_cv_counts(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(text(
            "SELECT a.area_id AS area,a.area_name,a.municipality_code AS municipality_code,"
            "count(l.listing_id) AS eligible_n,"
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY l.price_nightly::double precision) AS median_price_dkk,"
            "stddev_samp(l.log_price) AS sd_log_price,"
            "ST_XMin(a.geom_4326) AS bbox_west_lon,ST_YMin(a.geom_4326) AS bbox_south_lat,"
            "ST_XMax(a.geom_4326) AS bbox_east_lon,ST_YMax(a.geom_4326) AS bbox_north_lat,"
            "ST_Area(a.geom_25832)/1000000.0 AS polygon_area_km2 "
            "FROM spatial.official_cv_areas a "
            "LEFT JOIN features.listing_spatial_base s ON s.official_cv_area_id=a.area_id AND s.snapshot_date=:snapshot "
            "LEFT JOIN clean.airbnb_listings l ON l.snapshot_date=s.snapshot_date AND l.listing_id=s.listing_id "
            "AND l.primary_sample_candidate "
            "GROUP BY a.area_id,a.area_name,a.municipality_code,a.geom_4326,a.geom_25832 "
            "ORDER BY a.municipality_code,a.area_id"
        ), {"snapshot": SNAPSHOT}).mappings()]
    path = PROJECT_ROOT / "outputs/tables/phase04/cv_area_counts.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*rows[0], "boundary_source", "area_crs_epsg"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "boundary_source": "Official DAGI municipality / Copenhagen municipal bydel WFS",
                             "area_crs_epsg": 25832})
    return rows


def _rings(ax, geometry: dict, *, fill: str, edge: str = "#29465B", linewidth: float = 0.8,
           alpha: float = 1.0, outline_only: bool = False) -> None:
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for polygon in polygons:
        xs, ys = zip(*polygon[0])
        if outline_only:
            ax.plot(xs, ys, color=edge, linewidth=linewidth, alpha=alpha, zorder=3)
        else:
            ax.fill(xs, ys, facecolor=fill, edgecolor=edge, linewidth=linewidth, alpha=alpha, zorder=2)
            for hole in polygon[1:]:
                hx, hy = zip(*hole)
                ax.fill(hx, hy, facecolor="white", edgecolor=edge, linewidth=0.35, zorder=2)


def _map_frame(ax, fig, bounds, title: str, subtitle: str, source: str, *, legend=None) -> None:
    from matplotlib.patches import FancyBboxPatch

    xmin, ymin, xmax, ymax = bounds
    dx, dy = xmax - xmin, ymax - ymin
    pad = max(dx, dy) * 0.08
    ax.set_xlim(xmin - pad, xmax + pad)
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("#EEF4F7")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    x0 = xmin - pad + 0.74 * (dx + 2 * pad)
    y0 = ymin - pad + 0.06 * (dy + 2 * pad)
    ax.add_patch(FancyBboxPatch((x0 - 320, y0 - 190), 2640, 660,
                                boxstyle="round,pad=0,rounding_size=70", facecolor="white",
                                edgecolor="none", alpha=0.84, zorder=9))
    ax.plot([x0, x0 + 2000], [y0, y0], color="#182C3A", linewidth=2.5, zorder=10)
    ax.plot([x0, x0], [y0 - 120, y0 + 120], color="#182C3A", linewidth=1.5, zorder=10)
    ax.plot([x0 + 2000, x0 + 2000], [y0 - 120, y0 + 120], color="#182C3A", linewidth=1.5, zorder=10)
    ax.text(x0 + 1000, y0 + 180, "2 km", ha="center", va="bottom", fontsize=9,
            color="#182C3A", zorder=11)
    ax.annotate("N", xy=(0.93, 0.96), xytext=(0.93, 0.86), xycoords="axes fraction",
                textcoords="axes fraction", ha="center", va="center", fontsize=10,
                fontweight="bold", color="#182C3A", arrowprops={"arrowstyle": "-|>", "lw": 1.5,
                                                           "color": "#182C3A"})
    fig.text(0.06, 0.945, title, fontsize=17, fontweight="bold", color="#183449")
    fig.text(0.06, 0.902, subtitle, fontsize=9.3, color="#486174")
    fig.text(0.06, 0.037, source, fontsize=7.3, color="#506575")
    if legend:
        handles, labels = zip(*legend)
        fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.76, 0.82),
                   frameon=False, fontsize=9, handlelength=1.6, labelspacing=1.1)


def export_official_maps(engine) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    with engine.connect() as conn:
        municipalities = [dict(row) for row in conn.execute(text(
            "SELECT municipality_code,municipality_name,ST_AsGeoJSON(geom_25832) AS geojson "
            "FROM spatial.official_municipalities ORDER BY municipality_code"
        )).mappings()]
        neighbours = [dict(row) for row in conn.execute(text(
            "SELECT c.municipality_code,c.municipality_name,ST_AsGeoJSON(c.geom_25832) AS geojson "
            "FROM spatial.map_context_municipalities c CROSS JOIN spatial.study_area s "
            "WHERE s.area_kind='official_study_area' AND c.municipality_code NOT IN ('0101','0147') "
            "AND ST_DWithin(c.geom_25832,s.geom_25832,3500) "
            "ORDER BY c.municipality_code"
        )).mappings()]
        areas = [dict(row) for row in conn.execute(text(
            "SELECT area_id,area_name,municipality_code,ST_AsGeoJSON(geom_25832) AS geojson,"
            "ST_X(ST_PointOnSurface(geom_25832)) AS x,ST_Y(ST_PointOnSurface(geom_25832)) AS y "
            "FROM spatial.official_cv_areas ORDER BY area_id"
        )).mappings()]
        footprints = {row["area_kind"]: json.loads(row["geojson"]) for row in conn.execute(text(
            "SELECT area_kind,ST_AsGeoJSON(geom_25832) AS geojson FROM spatial.study_area "
            "WHERE area_kind='planned_15min_extraction'"
        )).mappings()}
        bounds = conn.execute(text(
            "SELECT ST_XMin(g),ST_YMin(g),ST_XMax(g),ST_YMax(g) "
            "FROM (SELECT ST_Extent(geom_25832)::geometry AS g FROM spatial.official_municipalities) x"
        )).one()
        extraction_bounds = conn.execute(text(
            "SELECT ST_XMin(g),ST_YMin(g),ST_XMax(g),ST_YMax(g) "
            "FROM (SELECT ST_Extent(geom_25832)::geometry AS g FROM spatial.study_area "
            "WHERE area_kind='planned_15min_extraction') x"
        )).one()
        centre = conn.execute(text(
            "SELECT ST_X(geom_25832),ST_Y(geom_25832) FROM spatial.reference_points "
            "WHERE reference_id='city_hall_square'"
        )).one()
    for row in municipalities + areas + neighbours:
        row["geometry"] = json.loads(row["geojson"])
    output = PhaseDirectory("figures", "phase04")
    output.mkdir(parents=True, exist_ok=True)
    palette = {"0101": "#A9C8D7", "0147": "#E9BF86"}
    source = ("Sources: DAGI/DAWA study + neighbouring municipalities; City of Copenhagen WFS bydel; "
              "acquired 29 Sep 2026. Distances: EPSG:25832.")
    context_legend = (Patch(facecolor="#E4EAE7", edgecolor="#A5B4B0"), "Neighbouring municipalities")

    def draw_neighbours(ax) -> None:
        for row in neighbours:
            _rings(ax, row["geometry"], fill="#E4EAE7", edge="#A5B4B0", linewidth=0.65)

    fig, ax = plt.subplots(figsize=(11, 7.5), dpi=180)
    fig.subplots_adjust(left=0.045, right=0.735, top=0.84, bottom=0.105)
    draw_neighbours(ax)
    for row in municipalities:
        _rings(ax, row["geometry"], fill="#B8D0D8", edge="#2C5969", linewidth=0.85)
    ax.plot(*centre, marker="*", markersize=11, color="#A54B32", markeredgecolor="white", zorder=5)
    _map_frame(ax, fig, bounds, "Study area", "Official municipal boundaries — Copenhagen and Frederiksberg",
               source, legend=[(Patch(facecolor="#B8D0D8", edgecolor="#2C5969"), "Study municipalities"),
                               context_legend,
                               (Line2D([], [], marker="*", markersize=10, linestyle="None", color="#A54B32"),
                                "City Hall Square reference")])
    fig.savefig(output / "phase04_study_area.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 7.5), dpi=180)
    fig.subplots_adjust(left=0.045, right=0.735, top=0.84, bottom=0.105)
    draw_neighbours(ax)
    for row in municipalities:
        _rings(ax, row["geometry"], fill=palette[row["municipality_code"]])
    _map_frame(ax, fig, bounds, "Municipalities", "Official DAGI/DAWA boundaries, not provider-labelled neighbourhoods",
               source, legend=[(Patch(facecolor=palette["0101"], edgecolor="#29465B"), "Copenhagen (0101)"),
                               (Patch(facecolor=palette["0147"], edgecolor="#29465B"), "Frederiksberg (0147)"),
                               context_legend])
    fig.savefig(output / "phase04_municipality_proxy.png", dpi=180)  # Legacy filename retained for links.
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 7.5), dpi=180)
    fig.subplots_adjust(left=0.045, right=0.735, top=0.84, bottom=0.105)
    draw_neighbours(ax)
    for row in areas:
        _rings(ax, row["geometry"], fill=palette[row["municipality_code"]], edge="#FFFFFF", linewidth=1.2)
        label = row["area_id"].removeprefix("cph_") if row["municipality_code"] == "0101" else "F"
        ax.text(row["x"], row["y"], label, ha="center", va="center", fontsize=8, fontweight="bold",
                color="#17384D", bbox={"facecolor": "white", "alpha": 0.77, "edgecolor": "none", "pad": 1.5},
                zorder=5)
    legend = [(Patch(facecolor=palette["0147"], edgecolor="#29465B"), "F  Frederiksberg"),
              context_legend]
    legend += [(Line2D([], [], linestyle="None", color="#17384D"),
                f"{row['area_id'].removeprefix('cph_')}  {row['area_name']}")
               for row in areas if row["municipality_code"] == "0101"]
    _map_frame(ax, fig, bounds, "Candidate geographic CV areas",
               "Ten official Copenhagen districts + Frederiksberg as one municipal unit; folds not fixed",
               source, legend=legend)
    fig.savefig(output / "phase04_candidate_cv_areas.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 7.5), dpi=180)
    fig.subplots_adjust(left=0.045, right=0.735, top=0.84, bottom=0.105)
    draw_neighbours(ax)
    _rings(ax, footprints["planned_15min_extraction"], fill="#DCECF0", edge="#53879A",
           linewidth=1.6, alpha=0.48)
    for row in municipalities:
        _rings(ax, row["geometry"], fill=palette[row["municipality_code"]], edge="#37546A")
    _rings(ax, footprints["planned_15min_extraction"], fill="none", edge="#53879A",
           linewidth=1.6, outline_only=True)
    _map_frame(ax, fig, extraction_bounds, "Planned OSM extraction area",
               "1.5 km buffer around official study geography and valid listing locations",
               source, legend=[(Patch(facecolor="#DCECF0", edgecolor="#53879A"), "Planned 15-min extraction footprint"),
                               (Patch(facecolor=palette["0101"], edgecolor="#37546A"), "Copenhagen"),
                               (Patch(facecolor=palette["0147"], edgecolor="#37546A"), "Frederiksberg"),
                               context_legend])
    fig.savefig(output / "phase04_osm_coverage.png", dpi=180)
    plt.close(fig)
