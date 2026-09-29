"""Guard the explicit ten-district plus one-municipality analysis geography."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.pipeline.run_minimum_pipeline import (
    AIRBNB_TO_STATBANK,
    join_analysis_area_context,
    join_statbank_context,
)


class ContextGeographyTest(unittest.TestCase):
    def test_frederiksberg_is_flagged_single_analysis_area(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "src.pipeline.run_minimum_pipeline.PROJECT_ROOT", Path(directory)
        ):
            root = Path(directory)
            district_path = root / "district.csv"
            municipality_path = root / "municipality.csv"
            districts = list(dict.fromkeys(AIRBNB_TO_STATBANK.values()))
            pd.DataFrame(
                {
                    "statbank_district_code": [str(i) for i in range(10)],
                    "district_name_statbank": districts,
                    "population_count": [100] * 10,
                    "household_count": [50] * 10,
                    "average_disposable_income_dkk": [300000] * 10,
                    "dwelling_count": [60] * 10,
                    "resident_count_statbank": [90] * 10,
                }
            ).to_csv(district_path, index=False)
            pd.DataFrame(
                {
                    "municipality_code": ["101", "147"],
                    "municipality_population_count": [670389, 105947],
                    "municipality_household_count": [332181, 55393],
                    "municipality_average_disposable_income_dkk": [295836, 344810],
                    "municipality_dwelling_count": [355352, 57781],
                }
            ).to_csv(municipality_path, index=False)
            metadata_root = root / "data" / "metadata"
            metadata_root.mkdir(parents=True)
            city_periods = {"KKBEF1": ("var5", "2026Q3"), "KKHUS1": ("var5", "2026Q1"), "KKIND3": ("var5", "2024"), "KKBOL3": ("var6", "2026")}
            national_periods = {"FOLK1A": "2026Q3", "FAM55N": "2026-01-01", "INDKP106": "2024", "BOL101": "2026"}
            (metadata_root / "copenhagen_statbank_run.json").write_text(json.dumps({
                "tidy_context": "district.csv",
                "tables": [{"table": table, "selected_labels": {variable: [period]}} for table, (variable, period) in city_periods.items()],
            }))
            (metadata_root / "municipality_statbank_run.json").write_text(json.dumps({
                "tidy_context": "municipality.csv",
                "tables": [{"table": table, "period": period} for table, period in national_periods.items()],
            }))
            listings = pd.DataFrame(
                {"airbnb_neighbourhood": [
                    next(alias for alias, district in AIRBNB_TO_STATBANK.items() if district == name)
                    for name in districts
                ] + ["Frederiksberg"]}
            )
            joined, district_summary = join_statbank_context(listings, district_path)
            joined, area_summary = join_analysis_area_context(joined, district_path, municipality_path)

        self.assertEqual(len(joined), 11)
        self.assertEqual(district_summary["listings_with_statbank_context"], 10)
        self.assertEqual(area_summary["analysis_areas"], 11)
        frederiksberg = joined.loc[joined["airbnb_neighbourhood"] == "Frederiksberg"].iloc[0]
        self.assertTrue(pd.isna(frederiksberg["population_count"]))
        self.assertTrue(pd.isna(frederiksberg["resident_count_statbank"]))
        self.assertFalse(frederiksberg["eligible_for_district_context_model"])
        self.assertTrue(frederiksberg["eligible_for_mixed_analysis_area_context"])
        self.assertTrue(frederiksberg["analysis_area_is_municipality_proxy"])
        self.assertEqual(frederiksberg["analysis_area_code"], "FRB_SINGLE_AREA_147")
        self.assertEqual(frederiksberg["analysis_area_population_count"], 105947)
        self.assertEqual(frederiksberg["analysis_area_households_period"], "2026-01-01")
        self.assertFalse(frederiksberg["analysis_area_household_period_differs"])
        self.assertTrue(frederiksberg["analysis_area_household_definition_unverified"])
        self.assertEqual(frederiksberg["analysis_area_households_reference_date"], "2026-01-01")
        self.assertTrue(joined.loc[0, "eligible_for_district_context_model"])
        self.assertEqual(joined.loc[0, "analysis_area_households_period"], "2026Q1")
        self.assertFalse(any(column.startswith("municipality_") for column in joined.columns))


if __name__ == "__main__":
    unittest.main()
