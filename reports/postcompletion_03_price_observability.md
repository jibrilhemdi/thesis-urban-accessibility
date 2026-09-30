# Post-completion amendment 3 — price observability by scrape batch

Completed 2026-09-29. **POST-COMPLETION OUTCOME-OBSERVABILITY ROBUSTNESS**, not a revision of the frozen Phase 9 analysis. This tests whether the original accessibility and validation conclusions depend on including priced listings from scrape dates with mostly unobserved prices. The outcome remains `ln(price_nightly)`, with listed nightly price in user-confirmed DKK. No missing or non-positive price was imputed, replaced from another listing, or fitted.

## Population and pre-fit rule

The observability denominator is all **21,080** listings in `analysis.analysis_dataset_v1` satisfying Copenhagen/Frederiksberg study area, `Entire home/apt`, the six Phase 2 conventional residential property categories, and valid coordinates, **before** applying price eligibility. A valid price means the view's observed-positive-price flag is true. Source `last_scraped` identifies the batch. Each current listing ID occurs once in this population; these are not repeated observations whose prices can be carried across dates.

Before fitting, the rule was registered as: retain a scrape date when **at least 90%** of otherwise eligible listings have a valid positive source price. The threshold was not selected using model scores.

| Source `last_scraped` | Otherwise eligible | Valid price | Missing/invalid price | Valid-price rate | Meets ≥90%? |
|---|---:|---:|---:|---:|:---:|
| 2026-06-30 | 8,954 | 8,101 | 853 | 90.47% | Yes |
| 2026-07-01 | 3,884 | 3,808 | 76 | 98.04% | Yes |
| 2026-07-03 | 3,972 | 369 | 3,603 | 9.29% | No |
| 2026-07-04 | 4,270 | 243 | 4,027 | 5.69% | No |
| **Total** | **21,080** | **12,521** | **8,559** | **59.40%** | — |

Thus missing-price status is **strongly scrape-batch dependent**: the early dates have 90–98% observed prices, but the July 3–4 dates have only 6–9%. The June 30 batch passes the declared cutoff narrowly; no alternative cutoff was searched. These figures describe observability, not the cause of missingness.

## Filtered model sample and methods

The Phase 9 common model sample is 12,412 observed-positive-price listings with an official validation area and reachable walking station. Intersecting it with the qualifying **June 30–July 1** dates retains **11,808 (95.13%)**, excluding 604 priced July 3–4 listings; it is not a new primary sample. The 101-row difference between the 11,909 pre-price-population early valid prices and this 11,808-row common sample follows Phase 9's official-area/reachable-station requirements, not an additional price exclusion.

The retained median listed price is **1,742.37 DKK** (original common sample **1,737.45 DKK**); the retained mean is **2,040.68 DKK** (original **2,027.03 DKK**), and retained quartiles are **1,369.50–2,362.40 DKK**. Every official validation area retains **94.27–96.02%** of its Phase 9 listings; every one of the six property types remains represented. Apartment/condo/rental-unit composition and area-specific price summaries are in `price_observability_sample_profile.csv`.

The existing Phase 9 five random-fold and eleven leave-one-official-area-out labels were **filtered, never reassigned**. All 16 test folds remain; the smallest geographic test fold is Brønshøj-Husum with **211** listings. Frederiksberg remains a municipality-sized validation area, not a Copenhagen district. Original Phase 9 M0 (property/host, municipality, City Hall distance), ME (M0 plus 800 m Euclidean food/cultural counts and nearest rail/metro station distance), and MW (M0 plus matched 10-minute walking counts and nearest-station walking time) were rerun using Phase 9 OLS and XGBoost procedures. OLS learned median/one-hot preprocessing is training-fold-only; XGBoost uses the frozen three-candidate grid and four spatially grouped inner training folds. RMSE and MAE are in **natural-log DKK-price units**; R² is out-of-fold. The optional area-context `_CTX` models were not run, keeping this a targeted observability check rather than mixing it with the separate, provisional context amendment.

## Result relative to frozen Phase 9

`ΔE` and `ΔW` below are the **within-sample** reductions in pooled out-of-fold RMSE versus that sample's own M0. Positive means accessibility helps prediction. The full 12-row table also gives Phase 9 and restricted RMSE, MAE and R² for every model and validation scheme.

| Estimator / validation | Phase 9 ΔE | Restricted ΔE | Phase 9 ΔW | Restricted ΔW |
|---|---:|---:|---:|---:|
| OLS / random | +0.00517 | +0.00532 | +0.00380 | +0.00396 |
| OLS / geographic | +0.00670 | +0.00696 | +0.00393 | +0.00421 |
| XGBoost / random | +0.00902 | +0.00927 | +0.00840 | +0.00923 |
| XGBoost / geographic | +0.00482 | +0.00406 | +0.00301 | +0.00277 |

**RQ2 — added accessibility information:** the original positive M0-to-ME and M0-to-MW predictive increments survive the restriction under both estimators and both validation schemes. Their magnitude remains modest under geographic XGBoost validation. This supports the *same qualified predictive conclusion*, not a causal claim and not a timetable/GTFS result. Geographic XGBoost MW improves on M0 in **7/11** held-out areas in both samples; ME improves in **7/11** original and **8/11** restricted areas. Benefits are not universal. Separately, the post-completion area-context amendment found weaker context-adjusted increments; the present no-context sensitivity does not undo that qualification.

**RQ3 — geographic versus random validation:** geographic error remains higher. For XGBoost MW, restricted random/geographic RMSE is **0.30712/0.32617** (gap **0.01905**), versus frozen Phase 9 **0.31205/0.32976** (gap **0.01771**). XGBoost M0 and ME also retain positive gaps; the restricted gaps are **0.01258** and **0.01779** respectively. Filtering therefore does not remove the random/geographic performance difference.

**Euclidean versus walking:** on the restricted sample, geographic XGBoost ME RMSE is **0.32488** versus MW **0.32617**; the corresponding frozen Phase 9 figures are **0.32795** and **0.32976**. Euclidean remains slightly lower-error in geographic validation. Restricted random XGBoost ME and MW are nearly tied (**0.30709** versus **0.30712**). There is no new evidence of a robust walking-over-Euclidean predictive advantage. OLS gives the same geographic ordering. These measures are different representations of access, but predictive ranking is small and fold-dependent.

The raw restricted RMSEs are somewhat lower than the Phase 9 RMSEs, but **the held-out population changed**. Those absolute values are not paired errors and must not be presented as evidence that filtering improved the estimator. Compare accessibility increments *within* each sample and inspect area-level paired increments, rather than treating the cross-sample RMSE difference as a treatment effect.

## Thesis limitation and integrity

Suggested thesis wording: *Price availability varies sharply by Airbnb scrape batch. Restricting analysis to the two dates with at least 90% observed prices retains 95% of the original model sample and leaves the substantive accessibility and geographic-validation patterns broadly intact. However, this does not establish that the missing prices are random, nor that results generalise to the many late-batch listings without observed prices. The analysis concerns observed listed prices, not transactions or occupancy.* The rule cannot recover missing outcomes or establish why they are absent. The OSM extraction also postdates the Airbnb price snapshot, as documented in Phase 9.

The runner verifies the frozen Phase 9 file hashes and all saved CV-assignment rows before and after modelling. No raw source, Phase 9 artifact, stored fold assignment, analytical database NULL, or original primary result was changed. Published outputs contain aggregate counts/metrics only; no host names, listing IDs or row-level coordinates.

Reproduce with `make observability-audit`, `make observability-models`, and `make observability-test` after the documented database setup. Code: `src/pipeline/run_price_observability_postcompletion03.py`; QA: `tests/test_price_observability_postcompletion03.py`. Aggregate outputs under `outputs/tables/` are `price_observability_by_scrape.csv`, `price_observability_sample_profile.csv`, `price_observability_fold_counts.csv`, `price_observability_performance.csv`, `price_observability_fold_performance.csv`, `price_observability_tuning.csv`, `price_observability_comparison.csv`, `price_observability_geographic_pairs.csv`, and `price_observability_metadata.json`. The thesis proposal's RQ2/RQ3 definitions were checked against the local scientific thesis proposal document; the operational interpretation here uses the frozen Phase 9 models and saved validation assignments.
