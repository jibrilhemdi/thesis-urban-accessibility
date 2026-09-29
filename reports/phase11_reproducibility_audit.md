# Phase 11 — reproducibility and packaging audit

Date: 2026-09-29. Scope: rebuild Phases 1–10 from the archived raw inputs, verify the primary freeze and database integrity, and package a guarded command interface. This is an **audit**, not a new analytical specification or model-selection phase.

## Rebuild performed

The full `src.pipeline.rebuild_phase11` workflow ran in a **separate, initially empty PostgreSQL database** and private temporary checkout containing copies of the 58 immutable raw files. The existing thesis database and its published `outputs/` were not used as destinations. The temporary checkout used the same installed Python 3.13.5 interpreter/packages as this workspace; a freshly resolved Python installation was **not** independently exercised. No data were downloaded during the rebuild.

In order, the workflow applied all **15** checksum-verified migrations; imported and cleaned the Airbnb listing/calendar/review/lookup files; imported versioned StatBank sources; loaded official boundaries; reconstructed canonical OSM destinations and Euclidean features; built the 545,903-node/1,234,730-directed-arc pedestrian network and walking features; created the analytical view and saved CV assignments; reran Phase 9 primary OLS/XGBoost and figures; reran Phase 10 robustness/bus/spatial-error work; and passed the final Phase 11 audit. The rebuilt Phase 2 import had **23,144 listings**, **8,448,291 calendar rows**, and **471,781 review rows**. The Phase 7 view had **13,860** observed positive prices, **9,284** missing/invalid prices, and the frozen common model sample of **12,412**. There were five random and 11 official-area CV folds.

The isolated database passed **21/21** additional provenance/integrity checks and **61/61** unit/live integration tests. The existing database separately passed **21/21** audit checks and the full pre-Phase-11 **59/59** suite; the two new rebuild-safety tests also passed. The checks cover source/migration hashes, source registration, one-row-per-listing keys, geometry validity and EPSG:4326/25832, feature cardinality, DKK positive-price/log relationship, fold coverage, walking-speed units, public CSV header privacy, training-only median/tuning and the frozen Phase 9/CV hashes. This is not a proof against every possible form of leakage; the testable pipeline safeguards and saved assignments are what were verified.

## Comparison with the frozen results

- The rebuilt CV assignment SHA-256 digest was **identical** to the original. The Phase 9 pooled-model and fold-performance CSVs were byte-identical; **26/27** Phase 9 table/figure artifacts had matching hashes, including all nine primary figures. The sole difference was `run_metadata.json`.
- That metadata difference was **not only a timestamp**: the original Phase 9 run recorded pandas **2.2.3**, whereas this rebuild used pandas **2.3.3**. Its completion timestamp also necessarily changed. Despite that environment difference, the saved primary results and figures were byte-identical. The current direct-dependency specification pins pandas 2.3.3; an exact environment recreation of the original 2.2.3 run remains untested.
- Across Phase 10, **21/24** common artifacts were byte-identical. The 524-row `fold_performance.csv` differed only in **column order**; after aligning columns, every cell matched. The two remaining differences were `primary_freeze.json` and `run_metadata.json`, because the changed Phase 9 metadata hash propagates into those manifests. No substantive Phase 10 result or fold metric changed.

These comparisons establish numerical and figure-output reproduction for this archive and interpreter, **not** that a future download or arbitrary OS/package resolver will recreate the identical snapshot/bytes.

## Command interface and environment

[`make reproduce`](../Makefile) runs the complete offline workflow in dependency order, then `make test` and `make audit` verify it. Its preflight refuses existing generated outputs, an already migrated database, or registered/clean rows before any phase starts. It does not delete/recreate a database, reset a Docker volume, overwrite raw data, download a new OSM extract, or promote Phase 10 sensitivities into the frozen primary model. The individual `phaseN-run` targets remain for diagnostics. Full instructions, data-source routes, architecture and limitations are in [`docs/reproducibility.md`](../docs/reproducibility.md) and the README.

Observed environment: macOS **26.5.2 arm64**, Python **3.13.5**, GDAL **3.8.5**, PostgreSQL **16.9**, PostGIS **3.5**, Docker image tag `postgis/postgis:16-3.5` under amd64 emulation. Selected direct package versions are pinned in [`requirements.txt`](../requirements.txt); the actual installed versions are written by `make audit` to `outputs/tables/phase11/audit.json`. Outer random seed **20260929**, inner XGBoost tuning seed **20260930**, and 1.5-km block seed **20261034** are preserved in code/metadata. `pip check` on the current `--system-site-packages` environment reports two unrelated inherited conflicts: `s3fs` versus `fsspec`, and `streamlit` versus `protobuf`. They did not prevent the full rebuild/tests, but the Python environment is not a clean locked dependency graph. Use a clean Python 3.13.5 venv for a future independent install test.

## Public-repository safety

The existing `.gitignore` excludes `.env`, raw Airbnb rows/reviews, the large OSM PBF, generated tables/figures and `.venv`; `git ls-files` returned only `.gitkeep` placeholders under `data/raw/` and `outputs/` and did not list `.env`. `.env.example` has no password value. The audit scanned generated CSV headers for listing/host identifiers, row-level coordinates, raw prices and review text; no prohibited column was found. **This header scan does not inspect every cell** for accidental text leakage, so human review is still required before releasing aggregate files. After the comparison and tests, the separate scratch database and 233 MB private temporary checkout (including its copied raw archive) were removed; the original raw archive and thesis database remain intact. The scratch copy/database were disposable and are not recoverable, but their source data remain in the original archive.

## Remaining limitations and disposition

1. The 2026 Inside Airbnb/OSM/statistical extracts are local immutable archives, not committed data. Their exact vintages may no longer be downloadable. A researcher needs an authorised copy of the archive and must verify checksums; reacquiring current data would constitute a new analysis version.
2. Direct Python packages are pinned, but transitive wheels and the Docker image tag are not digest-locked; the clean-room run reused the current interpreter rather than reinstalling all packages. Original Phase 9 metadata used pandas 2.2.3, whereas the verified rebuild used 2.3.3.
3. Some timestamps and CSV column order are not byte-stable, even where statistical values are. Compare canonical keys/values and output semantics, not metadata timestamp bytes. A future packaging improvement could canonicalise aggregate CSV column ordering and pin a full environment/image digest, without changing frozen models.
4. The thesis retains its substantive limitations: prices are listings rather than transactions, source DKK is user-confirmed, many prices are unobserved, Airbnb points are approximate, OSM is newer than listings, and Frederiksberg is a municipality proxy. No causal claim is warranted.

**Disposition:** the end-to-end database/pipeline rebuild, primary results, figures, folds and tests reproduced successfully from the archived raw inputs. Packaging is usable with the stated archive and environment caveats. No Phase 9 primary result, raw file, or modelling choice was changed in Phase 11. Stop here.

## Post-audit output-layout amendment

After this audit, 106 aggregate output files were reorganized into zero-padded phase subfolders with short basenames (for example `outputs/tables/phase09/model_performance.csv`). The one-time mapping and pre-move hashes are in `outputs/tables/phase11/layout_migration.json`. The 27 frozen Phase 9 artifact bytes and CV assignment hash stayed unchanged; only path keys in the Phase 10 freeze manifest and its dependent metadata hash changed. Existing audit statistics above refer to the same files and database state, not to a new model run.
