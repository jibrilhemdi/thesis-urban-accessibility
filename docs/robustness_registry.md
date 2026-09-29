# Phase 10 robustness registry — registered before Phase 10 estimation

Date: 2026-09-29. Phase 9 sample, outcome, 800 m/10 min accessibility, models, tuning decisions, random/geographic folds and published results are frozen. This registry classifies *timing*, not statistical significance. Category A includes pre-Phase-9 specifications and additional analyses requested in the Phase 10 brief **before Phase 10 fitting**; these are distinguished below to avoid falsely claiming Phase 7 preregistration.

| Analysis | Class | Documentary status and intended comparison |
|---|---|---|
| Apartment/condo-only | A — Phase 10 planned | Newly specified in Phase 10 brief; `Entire rental unit` + `Entire condo`, fixed by Phase 2 taxonomy; M0 vs MW, OLS/XGBoost, saved folds. Not in the Phase 7 freeze. |
| Reviewed-listings-only | A — Phase 10 planned | Newly specified in Phase 10 brief; `number_of_reviews>0`, otherwise unchanged. Not a primary inclusion rule. |
| Review/reputation controls | A — Phase 7 pre-specified | Review count and overall rating as secondary proxies, with rating missingness explicitly handled; not location/value subratings. |
| 15- and 20-minute walking accessibility | A — Phase 7 pre-specified | Match 1,200/1,600 m Euclidean counts; 10 min/800 m remains primary. |
| 1st/99th percentile price trimming | A — Phase 7 pre-specified | Training-fold cutoffs, applied to held-out records with test selection transparently reported. No outcome imputation. |
| Area fixed-effect OLS association | A — Phase 7 pre-specified | Within-area association, not unseen-area prediction. |
| Buffered geographic CV (500/1,000 m) | A — Phase 8 pre-specified | Saved `analysis.cv_buffer_exclusions` and unchanged area test sets. |
| Geometric spatial-block CV (1.5 km) | A — Phase 8 pre-specified | Saved `analysis.cv_assignments.block_1500m_fold`. |
| Spatial error/econometric association | A — Phase 10 planned conditional | Run one justified model if Phase 9 residual Moran diagnostic and implementation permit; not a predictive-CV replacement. |
| Opportunity-count-only assigned sample (12,508) | A — Phase 7 pre-specified, deferred | Drops station time from all compared models and adds the 96 assigned disconnected-station listings; a **different** feature definition and sample, not a direct Phase 9 metric replacement. Not estimated in the requested core A–J set. |
| Copenhagen-only / exclude Frederiksberg | A — Phase 7 pre-specified, deferred | Avoids municipality-level Frederiksberg context and its unseen-municipality LOAO fold; needs a separately labelled ten-area evaluation. Not estimated in the requested core A–J set. |
| Near-official-border exclusion | A — Phase 7 pre-specified, deferred | Coordinate uncertainty diagnostic; exact 100 m border flag already exists, but no phase-10 rerun in the requested core A–J set. |
| Complete-case bedrooms | A — Phase 7 pre-specified, already Phase 9 | Phase 9 produced the full-sample explanatory complete-case OLS table (12,289 listings); it is not refitted or silently relabelled as a new Phase 10 model. |
| Copenhagen-only district-context model | A — Phase 7 exploratory pre-plan, deferred | Unverified polygon/StatBank vintage and only ten independent area values; no harmonised pooled neighbourhood income/density. Do not force an unsupported primary context covariate. |
| Bus-stop walking proximity | B — post-Phase-9 methodological extension | **Chronology correction:** simple Euclidean bus-stop proximity was amended *before* Phase 9 and evaluated there. Phase 10 adds conservative bus-point deduplication and walking-network nearest-stop time, keeping the Phase 9 bus results and primary MW untouched. Rail/metro/S-train remains the primary transport definition. No frequency, waiting-time, route or reachable-destination claim. |
| GTFS multimodal transit | C — optional extension | Only if approved valid GTFS arrives after core robustness work. |
| TabICLv2 benchmark | C — optional extension | Predictive estimator only, never an imputer. |
| TabPFN imputation | C — optional extension | Only if material predictor missingness warrants it; training-only and never price imputation. |
| Coordinate-uncertainty band | C — optional extension | Only with source-supported uncertainty radius and feasible threshold analysis. |
| All-room-types market | C — optional extension | Distinct population with explicit room-type control, not a primary substitute. |

**Why the later bus amendment exists:** after Phase 9 we recognised that primary MW still focuses on rail/metro/S-train and that its existing secondary bus measure was only straight-line stop proximity. Phase 10 therefore adds *routed walking time* to a bus stop as a further secondary check. This does not retroactively move the earlier Euclidean bus amendment to after Phase 9.

Primary comparison uses the saved Phase 9 12,412 eligible observations whenever logically possible, same outer assignments, seed 20260929, four grouped inner folds (20260930), frozen three XGBoost candidates, training-only preprocessing, pooled and fold-level RMSE/MAE/R². Subset/trim analyses must disclose their changed evaluation populations. All prices are user-confirmed DKK before log transformation; all metric distances use EPSG:25832 and 4.8 km/h means 80 m/min.

## Completion record — 2026-09-29

- **Completed (A, as timing classified above):** apartment/condo, reviewed-only, observed review-count control, matched 15/20-minute versus 1,200/1,600-m thresholds, fold-wise 1st/99th-price trimming, 11-area fixed-effect association, saved 500/1,000-m buffered leave-area-out CV, saved 1.5-km block CV, and one 8-NN heteroskedasticity-aware spatial-error association model. The spatial-error model was justified by frozen Phase 9 out-of-fold Moran diagnostics; it was not used for predictive ranking.
- **Completed (B):** conservative archived-bus-stop deduplication, Phase 6 network walking time, `MW_bus` comparison, OLS coefficient/VIF, aggregate spot checks and full-sample descriptive SHAP. Existing Phase 9 Euclidean bus proximity remains the earlier pre-fit amendment.
- **Not run (C):** GTFS (valid approved source absent), TabICLv2 (optional model would enlarge scope), TabPFN imputation (primary predictor missingness low; experimental method not needed for core conclusions), coordinate-error band (no source-supported radius), all-room-types (different market).
- **Deferred Phase 7 plans outside the user-requested A–J core:** station-free 12,508 candidate analysis, Copenhagen-only, near-border, guarded district-context analysis. Phase 9 already ran the complete-case-bedroom OLS sensitivity. These remain visible, not silently described as completed.
- **Primary conclusion changed?** No frozen result was altered. Predictive accessibility gains are mostly preserved but notably weakened/reversed in the buffered geographic XGBoost tests; within-area associations are substantially attenuated. The bus-walking increment is small and does not promote bus proximity into the primary model. See [the Phase 10 report](../reports/phase10_robustness_and_extensions.md) and the aggregate master/conclusion tables for qualification.
