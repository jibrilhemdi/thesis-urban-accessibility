# Phase 10 — robustness, transport sensitivity and analytical synthesis

Date: 2026-09-29. **This report does not supersede the frozen Phase 9 primary results.** All errors below refer to the natural logarithm of listed nightly price. The source numeric price is treated as DKK by user confirmation; the original listing file displays `$` without its own currency code. These are listed offers, not transactions.

## 1. Purpose

Test whether the Phase 9 finding—that accessibility modestly helps prediction beyond listing/property and conventional location controls, but walking accessibility does not clearly beat a matched straight-line measure—survives pre-planned population, threshold, outlier, geographic and inferential sensitivities. Test a **separate post-Phase-9 bus-walking addition** without changing the primary rail/metro/S-train feature definition. [The registry](../docs/robustness_registry.md) was created before Phase 10 model estimation.

## 2. Frozen Phase 9 baseline — PRIMARY RESULTS

The primary sample is the same **12,412** Copenhagen/Frederiksberg conventional entire homes with positive source price, valid coordinates, official CV area and reachable walking station. No review or availability filter and no price imputation. M0 is property/host controls plus municipality and City Hall distance; ME adds 800 m straight-line food/culture counts and nearest rail-station distance; MW replaces these with 10-minute walking counts and nearest rail-station walking time. Phase 9's combined MEW was explicitly exploratory. The 123 missing bedrooms in this sample receive a median and missingness indicator fitted inside every training split. Phase 9 random five-fold and 11-area leave-one-out labels, three XGBoost candidate settings, four grouped inner folds and seeds were reused unchanged.

| Frozen Phase 9 XGBoost | Random RMSE | Geographic RMSE |
|---|---:|---:|
| M0 | 0.32046 | 0.33277 |
| ME | 0.31143 | 0.32795 |
| MW | 0.31205 | 0.32976 |

Geographic MW improves upon M0 by **0.00301** RMSE, but is **0.00181 worse** than ME. Seven of 11 held-out areas improve under MW; four reverse, including `cph_04` (−0.01297 fold RMSE reduction). The median geographic XGBoost MW fold RMSE is 0.31938 (IQR 0.31300–0.33711). Random CV is more optimistic. Phase 9 geographic out-of-fold residual Moran's I remains 0.1173 for OLS MW and 0.1386 for XGBoost MW (directed row-standardised eight-nearest-neighbour weights, EPSG:25832; permutation p=0.002). See [the Phase 9 report](phase09_main_models.md), not this report, for all original model details and uncertainty.

All 18 Phase 9 table/metadata artifacts, nine figures and all 23,144 saved CV assignment rows were SHA-256 checked before and after Phase 10. The recorded hashes are in `outputs/tables/phase10/primary_freeze.json`; they matched. Phase 9 files, fits, assignments, thresholds, sample and model-selection decisions were not rewritten.

## 3. Robustness registry and comparison rules

[The registry](../docs/robustness_registry.md) distinguishes analyses documented before Phase 9 from analyses first requested in the Phase 10 brief but declared **before Phase 10 fitting**. It also records deferred Phase 7 sensitivities, optional extensions and the true bus chronology. The Phase 9 bus *straight-line* stop-proximity test was amended **before Phase 9**; Phase 10's conservative stop deduplication and **walking** bus time were added **after Phase 9**. Calling all bus work newly added after Phase 9 would misstate the decision log.

For each scenario, M0 and MW use identical observations, saved outer fold labels, the Phase 9 preprocessing pipeline structure, the same XGBoost candidates and training-only inner tuning. Random/geographic pooled out-of-fold RMSE is primary; MAE and R², all fold scores, geographic median/IQR and selected parameters are exported. Where sample or test membership changes, comparisons are **within** that scenario, never against a different-sample Phase 9 score as if directly paired. No outer test outcome enters tuning. The 1st/99th-price sensitivity is an explicit exception in *evaluation population*: bounds are calculated only on outer training prices, then applied to the held-out outcome for this predeclared trimmed-target evaluation. Its error is not the all-price population error.

## 4. Sample robustness — PRE-SPECIFIED / PHASE 10 PLANNED

The fixed Phase 2 property taxonomy defines apartments/condos as `Entire rental unit` or `Entire condo`: **11,209** listings, 1,203 fewer than primary. Geographic XGBoost M0/MW RMSE is **0.32683/0.32521** (MW gain 0.00162); OLS is **0.32961/0.32549** (gain 0.00412). Random XGBoost is 0.31609/0.30676. These are within-subset comparisons, not evidence that this population is inherently easier to predict than all properties. Composition changes unevenly by area: `cph_07` loses 145/221 primary listings and leaves only **76** apartment test listings, so its fold is fragile. Area-by-area attrition is in `sample_change_by_area.csv`.

The reviewed-only sample is **10,522** (1,890, or 15.2%, excluded). Geographic XGBoost M0/MW is **0.32536/0.32207** (gain 0.00329), OLS **0.32497/0.32045** (gain 0.00452); random XGBoost is 0.31241/0.30312. Review absence varies by area (about 11%–20% excluded), so this is an activity-selected market subset, not a revised primary sample or realised-demand analysis.

## 5. Review/reputation robustness — PRE-SPECIFIED

On the **unchanged 12,412**, a separate `log1p(number_of_reviews)` control adds observed review-history information to M0 and MW. It is a post-listing activity proxy, not an exogenous property characteristic. Geographic XGBoost M0+review/MW+review RMSE is **0.33264/0.32915** (gain 0.00349); OLS is **0.33449/0.33053** (gain 0.00396). The MW cultural coefficient remains positive (0.0711 versus frozen 0.0705); station and food terms also retain their sign and similar magnitude. Thus the Phase 9 incremental conclusion is not driven solely by omission of review count.

`review_scores_rating` is absent for **1,890/12,412** (15.2%); reviews-per-month is similarly unavailable for many unreviewed listings. They were **not** silently median-filled or inserted as if observed in the main review-control run. A rating-based explanatory model would require a separately labelled complete-case analysis and, for full-sample inference, proper multiple imputation; it is not claimed here. Location/value subratings are omitted because they overlap the price/accessibility constructs. Review count and recency are activity proxies, not bookings.

## 6. Accessibility thresholds — PRE-SPECIFIED

All thresholds use the same 12,412 listings and the same source destination sets. At 4.8 km/h, 10/15/20-minute walking budgets correspond to **800/1,200/1,600 m route lengths including snap connectors**; matching Euclidean radii are straight-line disks, not isochrones. Rail-station continuous distance/time terms stay in their respective E/W blocks. The 10-minute/800 m Phase 9 comparison remains primary.

| Geographic XGBoost | Euclidean RMSE | Walking RMSE | Walking − Euclidean |
|---|---:|---:|---:|
| 10 min / 800 m, primary | 0.32795 | 0.32976 | +0.00181 |
| 15 min / 1,200 m, sensitivity | 0.32504 | 0.32636 | +0.00132 |
| 20 min / 1,600 m, sensitivity | 0.32670 | 0.32659 | −0.00010 |

Both alternatives improve on frozen M0 (0.33277), but 15-minute walking still trails Euclidean and the 20-minute reversal is only **0.00010** RMSE in XGBoost; OLS still slightly favours Euclidean at 20 minutes. It does **not** establish a robust walking-over-Euclidean advantage or replace the primary threshold. The representations are empirically different despite high rank correlations: 99.4% of listings have different 800 m food versus 10-minute reachable-food counts (Spearman 0.963; median straight-line excess 33 POIs); cultural counts differ for 82.0% (Spearman 0.923; median excess 3). At 15/20 minutes the count difference persists. See `accessibility_representation.csv` and [the threshold figure](../outputs/figures/phase10/threshold_sensitivity.png).

## 7. Price-outlier robustness — PRE-SPECIFIED

Each outer training fold determines its own 1st/99th DKK cutoffs; the same frozen bounds then select that fold's test outcomes. Geographic lower bounds span **741–769 DKK** and upper bounds **5,500–6,605 DKK**; **285** of 12,412 geographically held-out records are excluded across folds (102 in `cph_01`). The geographically pooled evaluated N is **12,127**, versus 12,412 primary; random-fold evaluated N is 12,162. These scores must not be compared naively to the original all-price error because the target population changed.

Within the trimmed geographic evaluation, XGBoost M0/MW RMSE is **0.29865/0.29673** (gain 0.00191), OLS **0.29759/0.29391** (gain 0.00369). A separately labelled full-sample trimmed HC3 association model has N=12,162; food (−0.0210) and culture (+0.0670) retain their primary signs, while the station-minute coefficient weakens to −0.00110 and its interval crosses zero. The exact area removals and bounds are in `price_trim_by_area.csv`; no price is imputed or overwritten.

## 8. Area fixed effects — EXPLANATORY ROBUSTNESS

An 11-area fixed-effect OLS MW association model compares listings **within** official Copenhagen districts or the single Frederiksberg municipality proxy (no simultaneous municipality dummy or area-constant context). It is not an unseen-area LOAO prediction model. Adjusted in-sample R² is 0.4880. The station-minute coefficient is −0.00130 (HC3 95% CI −0.00264 to +0.00003), compared with frozen −0.00154. The food coefficient changes from −0.0207 to **+0.0094** (CI includes zero); the cultural coefficient attenuates from **+0.0705 to +0.0133** (CI +0.0011 to +0.0255). The between-area component evidently matters for the original coefficients. Neither primary OLS nor this fixed-effect estimate is causal; within-area unobserved confounding and imperfect small-area geographic context remain.

## 9. Geographic validation robustness — PRE-SPECIFIED

Saved Phase 8 buffer exclusions drop training listings within **500 m** or **1,000 m** of each held-out official polygon; the held-out area and its test N stay unchanged. Actual minimum retained separation is **500.0–501.7 m** or **1,000.0–1,001.3 m**, verified in EPSG:25832. The 500 m buffer removes **113–2,477** training listings by fold; 1,000 m removes **428–4,957**, with Frederiksberg's 1,000 m fold retaining only **6,151** of its 11,108 otherwise available training listings. These are more difficult training/support conditions, not a fair score contest with unbuffered fitting.

| Geographic XGBoost | M0 RMSE | MW RMSE | MW gain |
|---|---:|---:|---:|
| Unbuffered Phase 9 | 0.33277 | 0.32976 | +0.00301 |
| 500 m training gap | 0.33573 | 0.33629 | **−0.00056** |
| 1,000 m training gap | 0.33991 | 0.33965 | +0.00026 |

OLS retains positive but shrinking MW gains (+0.00255 and +0.00059). Under the 500 m buffer, XGBoost MW improves in **5/11** areas versus 7/11 unbuffered. The greater errors can reflect geographic separation **and** new covariate support/extrapolation, particularly at the municipality-sized Frederiksberg fold. The incremental MW signal is therefore **not uniformly robust to buffer design**.

The saved **1.5 km geometric five-fold** XGBoost comparison gives M0/MW **0.32685/0.32263** (gain +0.00422); OLS gives **0.32984/0.32758** (+0.00226). The block MW score lies between Phase 9 random (0.31205) and official-area (0.32976), consistent with geography-dependent generalisation. The block geometry/allocation was not redesigned after seeing scores. Per-fold training loss, separation and all RMSE/MAE/R² are in `buffer_train_loss.csv`, `buffer_separation.csv`, `fold_performance.csv` and `geographic_fold_summary.csv`.

## 10. Bus-stop accessibility amendment — POST-PHASE-9 ROBUSTNESS

The same checksum-verified **2026-09-26** BBBike Copenhagen PBF and previously selected Phase 9 bus tags (`highway=bus_stop`, or `public_transport=platform` with `bus=yes`) yield **4,351 source node/way objects**. A conservative, outcome-blind rule collapses only same-normalised-name objects within 3 m or two unnamed objects within 0.5 m; opposite-direction stops are otherwise preserved. This removes **16** co-located representations, leaving **4,335** canonical stop points in `spatial.bus_stops_canonical`. The Phase 9 `spatial.bus_stops` and `features.bus_stop_proximity` tables remain untouched. Source/raw checksums and rule/version are recorded in `bus_feature_metadata.json`; the OSM snapshot is about three months newer than the June listing snapshot.

`features.bus_accessibility` has one row for every **23,144** listing, EPSG:25832 straight-line nearest canonical stop distance, and nearest bus stop time along the persisted directed Phase 6 pedestrian graph including listing and stop snap connectors at **4.8 km/h = 80 m/min**. Routes and nearest stops may cross district/municipal boundaries; no artificial same-neighbourhood restriction is imposed. There are 140 unreachable/non-routable listings overall, **none** among the 12,412 model listings. In the primary sample, median straight-line bus distance is **130 m** (5th–95th percentile 30–307 m), median walking time **2.74 min** (0.68–5.84). Bus walking time correlates 0.112 with rail-station walking time and 0.180 with City Hall distance; a legitimate pooled neighbourhood population-density variable does not exist, so that requested correlation cannot be computed without fabrication. Aggregate centre/periphery/far-rail-close-bus/close-both spot checks are in `bus_spotcheck_groups.csv`; no private listing points are exported.

The explicit **MW_bus = frozen MW + bus walking minutes** model uses the identical 12,412 observations and saved outer folds. Geographic XGBoost RMSE is **0.32869** versus frozen MW **0.32976** (gain **0.00107**, 8/11 areas improve); random gain is **0.00027**. Geographic OLS gain is **0.00047**. These are small changes relative to 0.33 log-price RMSE and not strong evidence that simple proximity contributes materially to transferable prediction. The full-sample HC3 bus-minute coefficient is **+0.01318** (CI +0.00930 to +0.01706): farther from a mapped stop is associated with higher listed price conditional on the controls, not an effect of poorer bus *service*. Rail-minute coefficient changes only from −0.00154 to −0.00173; food/culture remain negative/positive. Bus-minute VIF is **1.10**, rail-minute VIF **1.21**; gross collinearity with rail is not the explanation. The fixed-configuration full-sample TreeSHAP bus contribution is 0.0121 mean absolute log units, descriptive and neither causal nor an out-of-fold gain. See `bus_vif.csv`, `bus_shap.csv`, [the paired fold table](../outputs/tables/phase10/geographic_fold_pairs.csv) and [the bus increment figure](../outputs/figures/phase10/bus_increment.png).

This remains **stop proximity only**: there is no frequency, route connectivity, transfer, waiting-time, operating-hour or reachable-destination measure. Neither it nor the earlier Phase 9 Euclidean bus proximity is promoted into M0/ME/MW/MEW. GTFS is still pending approval.

## 11. Spatial-error robustness — INFERENTIAL ONLY

Phase 9 residual Moran statistics are nontrivial and justify **one** spatial-error sensitivity. Using exactly the Phase 9 MW controls and 12,412 observations, PySAL [`spreg.GM_Error_Het`](https://pysal.org/spreg/generated/spreg.GM_Error_Het.html) fits a heteroskedasticity-aware spatial-error specification with the same directed row-standardised 8-nearest-neighbour EPSG:25832 weights used in the residual diagnostic. Estimated error parameter λ is **0.279** (reported SE 0.0144). Station/food/culture coefficients are **−0.00148/−0.01938/+0.06930**, close in direction and size to primary MW OLS **−0.00154/−0.02071/+0.07049**. Spatial-error parameterisation therefore does not remove these broad full-sample associations, but the area-fixed-effect attenuation still warns against strong local or causal interpretation. In-sample spatial-error fit is **not** compared with spatial-CV prediction. Versioned coefficients/SE and weights are in `spatial_error_coefficients.csv` and metadata.

## 12. Optional extensions actually run

**None.** GTFS has not been approved/provided, so no timetable-sensitive multimodal variable is invented. TabICLv2 predictive benchmarking was deferred to keep Phase 10 focused on the frozen OLS/XGBoost comparison; it is not an imputer. TabPFN-based predictor imputation was deferred because the primary selected predictors have only ~1% bedroom missingness and the experimental method would require separate training-only validation and licence/checkpoint audit. The coordinate-uncertainty band is deferred because no validated obfuscation radius supports a numeric exclusion width. All-room-types modelling is a different accommodation market. Other Phase 7 ideas not in the requested A–J core set—12,508-person opportunity-only station-free comparison, Copenhagen-only/near-border exclusions and guarded district context—remain clearly listed as deferred in the registry. The Phase 9 complete-case-bedroom OLS sensitivity already exists; it is not falsely counted as newly estimated Phase 10 work.

## 13. Conclusion-stability assessment

The reproducible claim-by-analysis judgements in `outputs/tables/phase10/conclusion_stability.csv` use coefficients, paired fold directions, matched predictive metrics and uncertainty, not a p-value winner rule.

| Thesis-level claim | Phase 10 assessment |
|---|---|
| C1: straight-line and walking access represent different opportunities | **Survives.** Matched counts differ for most listings at 10/15/20 minutes even though correlated. |
| C2: accessibility adds information beyond M0 | **Mostly survives, but weakly and conditionally.** Apartment/reviewed/review-control/trimmed/block runs retain MW gains; 500 m buffered XGBoost reverses the gain and 1,000 m makes it nearly zero. |
| C3: walking has incremental value beyond Euclidean | **Not established.** Primary and 15-minute geographic scores favour Euclidean; the 20-minute XGBoost reversal is negligible and not supported by OLS. |
| C4: geographically separated validation differs from random CV | **Survives.** All comparable sensitivity comparisons show higher separated-fold error; buffer separation widens the gap. |

Do not reduce the result to one pooled number. The paired official-area table shows accessibility and bus increments reverse in some districts. `cph_04` is a notable primary MW reversal; the apartment `cph_07` fold has only 76 test listings. These observations are limits to generalisation, not reasons to drop inconvenient folds.

## 14. What changed relative to Phase 9

Only **new secondary outputs**: migration `015`, canonical bus stop and walking bus feature tables, the robustness registry, fitted Phase 10 sensitivity metrics/coefficients, matched-accessibility/bus QA, one spatial-error association model, [a publication table](../outputs/tables/phase10/robustness_summary.md), [master CSV](../outputs/tables/phase10/robustness_summary.csv), [fold-pair CSV](../outputs/tables/phase10/geographic_fold_pairs.csv), [conclusion matrix](../outputs/tables/phase10/conclusion_stability.csv), and four interpretive figures. The bus walking result is labelled post-Phase-9. The 500 m buffered XGBoost reversal and fixed-effect coefficient attenuation **qualify** the strength and interpretation of the original conclusion.

## 15. What did NOT change

No primary sample, price outcome, DKK assumption, POI destination set (including the previously buffered beyond-municipality destinations), 10-minute threshold, main OLS/XGBoost formula, Phase 9 bus-Euclidean analysis, random/geographic assignments, XGBoost candidate/tuning decision or Phase 9 output changed. No observed price, other outcome, database predictor NULL, raw OSM file or source listing was filled or edited. Phase 10's 15/20-minute or bus score does not replace the 10-minute main analysis. The 1-km original Phase 7 grid fold remains saved but is not relabelled as a Phase 9 fit.

## 16. Limitations

- Price missingness among conventional entire homes is substantial (~40.6%), and no model here repairs selection into observable price.
- Source currency is user-confirmed DKK, not independently encoded in the `$` source string. Snapshot timing differs: Airbnb June/July versus OSM September 2026.
- Airbnb coordinates are approximate; source documentation does not establish a defensible displacement radius for threshold-band analysis.
- Frederiksberg is one municipality-sized CV/context proxy, not a Copenhagen district. Its held-out fold has an unseen municipality dummy and strong extrapolation; contextual district income/density are not harmonised pooled listing-level covariates.
- Fixed effects change the association estimand; spatial-error inference depends on the chosen eight-neighbour weights. Neither eliminates unobserved confounding or supports causality.
- Outer-fold scores share training data and are not independent replicate studies. Small area folds and high E/W collinearity make tiny ranking differences uncertain.
- Buffer tests reduce training size/support as well as spatial leakage. OSM stop proximity is not bus service accessibility.

## 17. Inputs required for a separate Phase 11 reproducibility audit

Preserve the immutable Inside Airbnb/OSM files and their `meta.source_files` hashes, running PostgreSQL 16.9/PostGIS 3.5 database, migrations `001`–`015`, Python 3.13 environment from `requirements.txt` (notably pandas 2.3.3 and spreg 1.9.1), `.env` kept outside Git, frozen Phase 9 outputs/CV hash manifest, and Phase 10 runner logs/metadata. Reproduction order is `make phase10-run`, then `make phase10-test`, after Phases 1–9 inputs exist. The frozen Phase 9 outputs must be restored intact; do **not** rerun `make phase9-run` to reproduce Phase 10. `phase10-run` verifies hashes before/after, and `primary_freeze.json` records them. SQL spatial QA uses EPSG:25832; public tables/figures are aggregate-only with no listing IDs, names, free text or point coordinates. A Phase 11 audit should independently verify the hash manifest, fold key identity, idempotent migration/reruns, database source registration, all outputs, environment versions and privacy suppression; this report does **not** perform or claim Phase 11 completion.
