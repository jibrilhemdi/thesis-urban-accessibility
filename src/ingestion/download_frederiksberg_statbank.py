"""Compatibility command for the corrected two-municipality StatBank collection.

The old Frederiksberg-only collector mixed municipality and district fields and
mislabelled a population count as a housing resident count. Its raw files remain
available for provenance, but new collections use the comparable collector.
"""

from src.ingestion.download_municipality_statbank import main


if __name__ == "__main__":
    main()
