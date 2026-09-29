.PHONY: db-up db-down db-connect db-migrate db-check db-version db-register db-ingest-sample db-test phase2-run phase2-test phase3-run phase3-test phase4-acquire-boundaries phase4-acquire-map-context phase4-run phase4-test phase5-acquire phase5-run phase5-test

db-up:
	docker compose --env-file .env up -d --wait --wait-timeout 120 db

db-down:
	docker compose --env-file .env down

db-connect:
	python -m src.db.cli connect

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
