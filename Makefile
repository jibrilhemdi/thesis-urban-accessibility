.PHONY: db-up db-down db-connect db-psql db-diagnose db-migrate db-check db-version db-register db-ingest-sample db-test phase2-run phase2-test phase3-run phase3-test phase4-acquire-boundaries phase4-acquire-map-context phase4-run phase4-test phase5-acquire phase5-run phase5-test phase6-run phase6-export phase6-test phase7-run phase7-test phase8-run phase8-test phase9-bus phase9-run phase9-test phase9-boundary-audit phase10-bus phase10-run phase10-spatial phase10-synthesis phase10-figures phase10-test reproduce audit test output-migrate context-audit context-audit-test context-models context-models-preflight context-models-test observability-audit observability-models observability-test final-outputs final-outputs-test final-output-revision final-output-revision-test boundary-audit boundary-models boundary-test validation-visuals destination-inventory boundary-catchment-figure release-check scientific-freeze-check final-presentation

db-up:
	docker compose --env-file .env up -d --wait --wait-timeout 120 db

db-down:
	docker compose --env-file .env down

db-connect:
	python -m src.db.cli connect

# Explicitly enter the Compose thesis DB; no host defaults or password on argv.
db-psql:
	docker compose --env-file .env exec db sh -c 'exec psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

# Read-only comparison of the configured thesis DB with a separate local server.
db-diagnose:
	.venv/bin/python -m src.db.diagnose

db-migrate:
	python -m src.db.cli migrate

db-check:
	python -m src.db.cli check

db-version:
	python -m src.db.cli postgis-version

db-register:
	python -m src.db.cli register-sources

db-ingest-sample:
	python -m src.db.cli ingest-csv --path data/raw/inside_airbnb/copenhagen/2026-06-30/visualisations/neighbourhoods.csv --table inside_airbnb_neighbourhoods

db-test:
	python -m unittest discover -s tests -p 'test_db_phase1.py' -v

phase2-run:
	python -m src.pipeline.run_airbnb_phase2

phase2-test:
	python -m unittest discover -s tests -p 'test_airbnb_phase2.py' -v

phase3-run:
	python -m src.pipeline.run_context_phase3

phase3-test:
	python -m unittest discover -s tests -p 'test_context_phase3.py' -v

phase4-acquire-boundaries:
	python -m src.pipeline.acquire_official_boundaries

phase4-acquire-map-context:
	python -m src.pipeline.acquire_map_context_boundaries

phase4-run:
	python -m src.pipeline.run_spatial_phase4

phase4-test:
	python -m unittest discover -s tests -p 'test_spatial_phase4.py' -v

phase5-acquire:
	python -m src.pipeline.acquire_osm_phase5

phase5-run:
	python -m src.pipeline.run_euclidean_phase5

phase5-test:
	python -m unittest discover -s tests -p 'test_euclidean_phase5.py' -v

phase6-run:
	.venv/bin/python -m src.pipeline.run_walking_phase6

phase6-export:
	.venv/bin/python -m src.pipeline.export_walking_phase6

phase6-test:
	.venv/bin/python -m unittest discover -s tests -p 'test_walking_phase6.py' -v

phase7-run:
	.venv/bin/python -m src.pipeline.run_analysis_phase7

phase7-test:
	.venv/bin/python -m unittest discover -s tests -p 'test_analysis_phase7.py' -v

phase8-run:
	.venv/bin/python -m src.pipeline.run_analysis_phase8

phase8-test:
	.venv/bin/python -m unittest discover -s tests -p 'test_analysis_phase8.py' -v

phase9-bus:
	.venv/bin/python -m src.pipeline.run_bus_proximity_phase9

phase9-run: phase9-bus phase9-boundary-audit
	.venv/bin/python -m src.pipeline.run_analysis_phase9

phase9-test:
	.venv/bin/python -m unittest discover -s tests -p 'test_analysis_phase9.py' -v

phase9-boundary-audit:
	.venv/bin/python -m src.pipeline.audit_destination_boundary_phase9

phase10-bus:
	.venv/bin/python -m src.pipeline.run_bus_walking_phase10

phase10-run: phase10-bus
	.venv/bin/python -m src.pipeline.run_analysis_phase10
	.venv/bin/python -m src.pipeline.run_spatial_error_phase10
	.venv/bin/python -m src.pipeline.run_analysis_phase10 --synthesis-only
	.venv/bin/python -m src.pipeline.run_analysis_phase10 --buffer-qa

phase10-spatial:
	.venv/bin/python -m src.pipeline.run_spatial_error_phase10

phase10-synthesis:
	.venv/bin/python -m src.pipeline.run_analysis_phase10 --synthesis-only

phase10-figures:
	.venv/bin/python -m src.pipeline.run_analysis_phase10 --figures-only

phase10-test:
	THESIS_PHASE10_TEST=1 .venv/bin/python -m unittest tests.test_analysis_phase10 -v

# Only for a fresh checkout and an empty database; refuses to overwrite outputs.
reproduce:
	.venv/bin/python -m src.pipeline.rebuild_phase11

audit:
	.venv/bin/python -m src.pipeline.audit_reproducibility_phase11

output-migrate:
	.venv/bin/python -m src.pipeline.migrate_output_layout

# Independent post-completion context audit; does not rerun price models.
context-audit:
	.venv/bin/python -m src.pipeline.run_context_postcompletion01

context-audit-test:
	THESIS_CONTEXT_AUDIT_TEST=1 .venv/bin/python -m unittest tests.test_context_postcompletion01 -v

context-models-preflight:
	.venv/bin/python -m src.pipeline.run_context_models_postcompletion02 --preflight

context-models:
	.venv/bin/python -m src.pipeline.run_context_models_postcompletion02

context-models-test:
	THESIS_CONTEXT_MODELS_TEST=1 .venv/bin/python -m unittest tests.test_context_models_postcompletion02 -v

observability-audit:
	.venv/bin/python -m src.pipeline.run_price_observability_postcompletion03 --audit-only

observability-models:
	.venv/bin/python -m src.pipeline.run_price_observability_postcompletion03

observability-test:
	THESIS_OBSERVABILITY_TEST=1 .venv/bin/python -m unittest tests.test_price_observability_postcompletion03 -v

final-outputs:
	.venv/bin/python -m src.pipeline.run_final_outputs_postcompletion04
	.venv/bin/python -m src.pipeline.revise_final_outputs_pre_freeze

final-outputs-test:
	THESIS_FINAL_OUTPUTS_TEST=1 .venv/bin/python -m unittest tests.test_final_outputs_postcompletion04 -v

final-output-revision:
	.venv/bin/python -m src.pipeline.revise_final_outputs_pre_freeze

final-output-revision-test:
	.venv/bin/python -m unittest tests.test_final_output_revision_pre_freeze -v

boundary-audit:
	.venv/bin/python -m src.pipeline.run_boundary_sensitivity_pre_freeze --audit-only

boundary-models:
	.venv/bin/python -m src.pipeline.run_boundary_sensitivity_pre_freeze

boundary-test:
	THESIS_BOUNDARY_TEST=1 .venv/bin/python -m unittest tests.test_boundary_sensitivity_pre_freeze -v

validation-visuals:
	.venv/bin/python -m src.pipeline.run_validation_visualisation_final

# Read-only Phase 5/PostGIS appendix export; does not rebuild accessibility.
destination-inventory:
	.venv/bin/python -m src.pipeline.export_destination_inventory_appendix
	.venv/bin/python -m src.pipeline.export_final_latex_tables

# Public-OSM appendix illustration only; no route/accessibility/model recomputation.
boundary-catchment-figure:
	.venv/bin/python -m src.pipeline.export_boundary_catchment_figure

# Validate an explicit public allowlist; never include raw data or local secrets.
release-check:
	.venv/bin/python -m src.pipeline.release_snapshot --check

# A new scientific release requires explicit authorization; this target checks v1 only.
scientific-freeze-check:
	.venv/bin/python -m src.pipeline.run_final_presentation --check-only

# Strictly aggregate-source presentation export; verifies scientific hashes before/after.
final-presentation:
	.venv/bin/python -m src.pipeline.run_final_presentation

test:
	THESIS_DB_TEST=1 THESIS_PHASE2_TEST=1 THESIS_PHASE3_TEST=1 THESIS_PHASE4_TEST=1 THESIS_PHASE5_TEST=1 THESIS_PHASE6_TEST=1 THESIS_PHASE7_TEST=1 THESIS_PHASE8_TEST=1 THESIS_PHASE9_TEST=1 THESIS_PHASE10_TEST=1 .venv/bin/python -m unittest discover -s tests -v
