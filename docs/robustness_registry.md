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

## FINAL PRE-FREEZE DESTINATION-BOUNDARY SENSITIVITY — registered 2026-09-29 before fitting

**Status:** post-Phase-9, post-completion sensitivity; not part of the Phase 7 freeze or a replacement for Phase 9. The primary buffered food/social, cultural/tourist and rail/metro/S-train destination sets remain unchanged. Restrict only canonical destination **endpoints** to the `ST_Covers` union of the existing official Copenhagen and Frederiksberg municipality polygons (EPSG:25832). Do not clip the persisted pedestrian graph or prohibit cross-district/municipality walking routes. Official areas are CV groups, never accessibility walls.

**Pre-fit comparison:** count retained/removed destinations and changes in the six primary-threshold access measures without examining price. Attempt the identical 12,412 primary listings; if a clipped station becomes unreachable, use one matched sample across M0_BOUND, ME_BOUND and MW_BOUND and disclose attrition. Fit only OLS and XGBoost M0/ME/MW with Phase 9 controls, 800 m/10-minute threshold, three frozen XGBoost candidates, training-only four-fold grouped tuning, seeds and saved five random/11 geographic outer folds. Report RMSE/MAE/R² pooled and by geographic area; compare to buffered Phase 9 only when samples match. This test cannot promote a lower-error clipped definition into the primary specification.

**Completion:** all 12,412 listings retained; clipped endpoint counts and six features passed price-blind QA. Both clipped access blocks still improve on M0 in pooled geographic validation, Euclidean remains lower-error than walking, and the pooled increments move by at most 0.000374 log-RMSE for the four geographic OLS/XGBoost comparisons. Changes cluster at the outer municipal-union edge. No primary conclusion or frozen Phase 9 artifact changed; see [`reports/pre_freeze_boundary_sensitivity.md`](../reports/pre_freeze_boundary_sensitivity.md).

**Why the later bus amendment exists:** after Phase 9 we recognised that primary MW still focuses on rail/metro/S-train and that its existing secondary bus measure was only straight-line stop proximity. Phase 10 therefore adds *routed walking time* to a bus stop as a further secondary check. This does not retroactively move the earlier Euclidean bus amendment to after Phase 9.

Primary comparison uses the saved Phase 9 12,412 eligible observations whenever logically possible, same outer assignments, seed 20260929, four grouped inner folds (20260930), frozen three XGBoost candidates, training-only preprocessing, pooled and fold-level RMSE/MAE/R². Subset/trim analyses must disclose their changed evaluation populations. All prices are user-confirmed DKK before log transformation; all metric distances use EPSG:25832 and 4.8 km/h means 80 m/min.

## Completion record — 2026-09-29

- **Completed (A, as timing classified above):** apartment/condo, reviewed-only, observed review-count control, matched 15/20-minute versus 1,200/1,600-m thresholds, fold-wise 1st/99th-price trimming, 11-area fixed-effect association, saved 500/1,000-m buffered leave-area-out CV, saved 1.5-km block CV, and one 8-NN heteroskedasticity-aware spatial-error association model. The spatial-error model was justified by frozen Phase 9 out-of-fold Moran diagnostics; it was not used for predictive ranking.
- **Completed (B):** conservative archived-bus-stop deduplication, Phase 6 network walking time, `MW_bus` comparison, OLS coefficient/VIF, aggregate spot checks and full-sample descriptive SHAP. Existing Phase 9 Euclidean bus proximity remains the earlier pre-fit amendment.
- **Not run (C):** GTFS (valid approved source absent), TabICLv2 (optional model would enlarge scope), TabPFN imputation (primary predictor missingness low; experimental method not needed for core conclusions), coordinate-error band (no source-supported radius), all-room-types (different market).
- **Deferred Phase 7 plans outside the user-requested A–J core:** station-free 12,508 candidate analysis, Copenhagen-only, near-border, guarded district-context analysis. Phase 9 already ran the complete-case-bedroom OLS sensitivity. These remain visible, not silently described as completed.
- **Primary conclusion changed?** No frozen result was altered. Predictive accessibility gains are mostly preserved but notably weakened/reversed in the buffered geographic XGBoost tests; within-area associations are substantially attenuated. The bus-walking increment is small and does not promote bus proximity into the primary model. See [the Phase 10 report](../reports/phase10_robustness_and_extensions.md) and the aggregate master/conclusion tables for qualification.

## POST-COMPLETION CONTEXT ROBUSTNESS — registered 2026-09-29 before fitting

This is a **post-Phase-9 and post-Phase-11 contextual extension**, not a Phase 7 pre-specified or Phase 9 primary result. The completed [11-area audit](../reports/postcompletion_01_context_audit.md) supplies provisional EPSG:25832 polygon population density and source-specific 2024 mean disposable income. The City/Frederiksberg income denominator is not proven harmonised, the City boundary vintage/water treatment is unverified, and Frederiksberg is a municipality-sized proxy. These caveats are part of the estimand, not a reason to alter the frozen primary model.

| Analysis | Status and sample | Fixed comparison before fitting |
|---|---|---|
| Mixed 11-area context ladder | Post-completion extension; exactly the Phase 9 12,412 where context is complete | M0_CTX, ME_CTX, MW_CTX, MEW_CTX = the corresponding Phase 9 block plus **only** log area population density and income in 100k DKK; same municipality indicator, saved random/geographic outer folds, three XGBoost candidates and grouped inner tuning. OLS HC3 is associational, not spatially robust. |
| Copenhagen-only harmonisation | Post-completion sensitivity; restrict the same eligible observations to ten City districts | M0_CTX, ME_CTX and MW_CTX, OLS associations and saved ten-area geographic XGBoost CV; no Frederiksberg municipality proxy or national income series. Retain original district fold identities and report changed N. |

Do not include official-area fixed effects, the income-definition flag or the municipality-proxy flag as simultaneous explanatory variables with the existing municipality indicator. Report fold-level as well as pooled RMSE/MAE/R²; compare Phase 9 and context increments only on identical observations. Context is area-constant, so listing count does not imply independent area-level information. No threshold, POI taxonomy, outcome, random seed, fold or primary result is revised.

### Completion record — 2026-09-29

- **Completed:** mixed 12,412-row M0_CTX/ME_CTX/MW_CTX/MEW_CTX OLS associations and saved random/geographic OLS/XGBoost comparisons; separate 11,108-row Copenhagen-only M0_CTX/ME_CTX/MW_CTX OLS associations and saved ten-district geographic CV. All planned fields, estimators and folds above were retained.
- **Matched conclusion:** geographic XGBoost ME and MW increments versus M0 shrink from +0.00482/+0.00301 in Phase 9 to +0.00004/−0.00056 with context; MEW_CTX has a small +0.00100 exploratory increment. Copenhagen-only MW_CTX gains +0.00091 versus its *own* M0_CTX but improves only 5/10 held-out districts. Context therefore qualifies, rather than replaces, the Phase 9 accessibility claim.
- **Integrity:** zero missing context in the frozen sample; all 27 Phase 9 artifact hashes and the full saved CV-assignment hash match after fitting. No primary model, outcome or raw data was changed. See [the post-completion model report](../reports/postcompletion_02_context_models.md).

## POST-COMPLETION OUTCOME-OBSERVABILITY ROBUSTNESS — registered 2026-09-29 before fitting

This is a targeted **post-Phase-9** sample-selection sensitivity, not a replacement for the primary result. Before any model fit, use all Copenhagen/Frederiksberg conventional entire homes with valid coordinates, regardless of price, to calculate valid-positive-price rates by source `last_scraped`. A date is a **high-completeness batch only if at least 90%** of these otherwise eligible listings have a valid positive price. This threshold is fixed independently of price-model performance; price is never imputed or copied between listings/dates.

Apply only those date labels to the *existing* 12,412-row Phase 9 common model sample, retaining the original positive-price, official-area and reachable-station rules. Keep its saved random and geographic outer fold labels and Phase 9 M0/ME/MW controls, 800 m/10-minute features, OLS/XGBoost estimators, three XGBoost candidates and grouped inner tuning. Compare OLS and XGBoost under both CV schemes using RMSE/MAE/R² and report changed sample composition/fold sizes. The optional `_CTX` extension is deferred to keep this amendment focused on outcome observability. No date restriction was chosen using model results.

**Pre-fit audit:** 2026-06-30 (8,101/8,954 = 90.47%) and 2026-07-01 (3,808/3,884 = 98.04%) meet the rule; 2026-07-03 (369/3,972 = 9.29%) and 2026-07-04 (243/4,270 = 5.69%) do not. The retained original-model sample has **11,808/12,412** rows (95.13%) and all 11 original geographic folds remain represented (minimum retained test N = 211). This is the frozen selection for the following robustness fit, not an intervention on missing outcomes.

### Completion record — 2026-09-29

- **Status:** post-completion outcome-observability robustness; completed OLS/XGBoost M0/ME/MW with the saved five random and eleven geographic outer folds. The optional `_CTX` models were not run. No Phase 9 primary result was changed.
- **Observability:** 12,521/21,080 otherwise eligible listings have a positive observed price; early-date batches pass the predeclared ≥90% rule, while 3–4 July do not. This is a scrape-date association, not proof of why prices are missing.
- **Conclusion stability:** accessibility remains incrementally predictive beyond Phase 9 M0 under both schemes, with modest geographic gains. Random-versus-geographic error gap persists. Euclidean remains slightly better than walking in pooled geographic OLS/XGBoost; no walking-over-Euclidean advantage emerged. Fold-level gains remain heterogeneous. The separate context-adjusted qualification is unchanged.
- **Integrity:** 11,808/12,412 original model listings retained; all geographic folds remain usable. The original 27 Phase 9 artifact hashes and full saved CV-assignment hash were checked before and after; no missing price was filled. See [the outcome-observability report](../reports/postcompletion_03_price_observability.md) and its aggregate tables.

## 2026-09-30 — presentation clarification, not a new robustness estimate

The earlier registration heading above accurately records *when* the context models were estimated. Their final scientific role is an **area-context-adjusted core specification** for RQ2, paired with the frozen Phase 9 **base specification**. Population density and income were conceptually planned, omitted from Phase 9 while source comparability remained unresolved, and estimated after the source audit. They were not frozen as the original Phase 7 primary model; mixed Copenhagen district/Frederiksberg municipality context remains provisional. This clarification changes no estimate, fold or sample. [Decision-log clarification](decision_log.md); [core RQ2 panel](../outputs/tables/final/table_rq2_area_context.csv).
