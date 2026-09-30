# Final pre-freeze sensitivity — destination endpoints at the study boundary

Date: 2026-09-29. **Status: post-Phase-9 endpoint-boundary sensitivity, not a new primary analysis.** The original buffered Phase 5/6 opportunity universe, Phase 9 models/results, and saved CV assignments remain frozen. This check changes only which canonical destination **points** are eligible. The shortest-path pedestrian graph is unchanged and may cross or briefly leave/re-enter administrative areas. The ten Copenhagen districts and Frederiksberg are validation groups, **not** accessibility barriers: listings can access destinations in other districts or in the other study municipality.

## Definition, population and reproducibility

Migration `017_destination_boundary_sensitivity.sql` creates the EPSG:25832 union of existing official Copenhagen (`0101`) and Frederiksberg (`0147`) municipality polygons, plus `ST_Covers` views of retained canonical food/social, cultural/tourist and rail/metro/S-train endpoints. It adds only the separate `features.destination_boundary_sensitivity` table. The original `spatial.osm_pois`, `spatial.transit_stations`, `features.euclidean_accessibility`, `features.walking_accessibility`, and `analysis.analysis_dataset_v1` are untouched. No new OSM source, taxonomy, network, speed, threshold, district restriction or outcome imputation is introduced.

The runner uses the existing canonical EPSG:25832 points for exact straight-line station metres and 800 m food/culture counts (a projected KD-tree, spot-checked against PostGIS `ST_Distance`/`ST_DWithin`). It rebuilds the same directed Phase 6 walking graph from the SHA-256-verified immutable PBF, verifies persisted node/segment/arc counts, reuses saved Phase 6 entity snaps and connector costs, then computes only 10-minute (800 m route) counts and nearest clipped station time at **4.8 km/h = 80 m/min**. It does not compute 15/20-minute, bus or GTFS variables. No price is queried until the price-blind destination and feature audits complete.

The frozen Phase 9 common sample is **12,412** positive-price DKK entire-home/conventional listings with official area and originally reachable walking station. Every one still has a clipped Euclidean and walking nearest station; **zero** are lost. M0_BOUND, ME_BOUND and MW_BOUND therefore use exactly the Phase 9 listings, saved five random/11 leave-one-official-area-out folds, original property/host/municipality/centrality controls, training-fold-only median plus missingness indicator and one-hot preprocessing, the same OLS procedure, three XGBoost candidates, four municipality-stratified grouped inner training folds, and seeds **20260929/20260930**. No MEW model was fit. Performance is pooled outer out-of-fold log-price RMSE/MAE/R²; full fold results and tuning choices are exported. `M0_BOUND` matches Phase 9 M0 exactly, confirming the matched comparison.

## Price-blind destination and feature audit

| Canonical destination category | Buffered | Retained in/on union | Removed outside |
|---|---:|---:|---:|
| Food/social | 3,006 | 2,315 | **691** |
| Cultural/tourist | 463 | 272 | **191** |
| Rail/metro/S-train | 143 | 65 | **78** |

| Primary-threshold listing measure | Changed N / 12,412 | Changed % | Primary minus clipped: mean | Range |
|---|---:|---:|---:|---:|
| Food/social, Euclidean 800 m count | 1,467 | 11.82% | +0.412 POIs | 0 to +24 |
| Food/social, walk 10-minute count | 883 | 7.11% | +0.172 POIs | 0 to +16 |
| Cultural/tourist, Euclidean 800 m count | 1,155 | 9.31% | +0.200 POIs | 0 to +5 |
| Cultural/tourist, walk 10-minute count | 382 | 3.08% | +0.076 POIs | 0 to +3 |
| Nearest rail station, Euclidean distance | 74 | 0.60% | −1.63 m | −769.98 to ~0 m |
| Nearest rail station, walking time | 80 | 0.64% | −0.034 min | −15.28 to 0 min |

Counts cannot increase when destinations are removed; nearest-station distance/time cannot decrease. All checks passed. Among listings with an altered measure, the external destination can be across either the municipality border or the study footprint's outer shoreline; the union boundary is not just an inland border. The aggregate distance-to-outer-union-boundary check finds **1,524/8,985 (16.96%)** with any change within 800 m, **1/3,277 (0.03%)** at 800–1,600 m, and **0/150** farther away. These bands use the projected polygon boundary and contain no public listing coordinates. An appendix map was unnecessary because this table already shows the concentration without adding a potentially misleading cartographic layer.

## Matched out-of-fold results

Positive gain means **M0 RMSE minus access-model RMSE**, so higher means lower held-out error after adding access. All RMSEs are natural-log listed-price units. The full [performance](../outputs/tables/boundary_sensitivity_performance.csv) and [comparison](../outputs/tables/boundary_sensitivity_comparison.csv) tables also give MAE/R² and random-fold results.

| Geographic CV | Buffered M0 | Buffered ME | Buffered MW | Clipped M0_BOUND | Clipped ME_BOUND | Clipped MW_BOUND |
|---|---:|---:|---:|---:|---:|---:|
| OLS RMSE | 0.334461 | 0.327761 | 0.330533 | 0.334461 | 0.327686 | 0.330647 |
| XGBoost RMSE | 0.332770 | 0.327946 | 0.329760 | 0.332770 | 0.327844 | 0.329387 |

| Geographic RMSE gain vs matched M0 | Buffered | Clipped | Change in gain |
|---|---:|---:|---:|
| OLS ME | +0.006700 | +0.006775 | +0.000075 |
| OLS MW | +0.003928 | +0.003814 | −0.000114 |
| XGBoost ME | +0.004824 | +0.004926 | +0.000102 |
| XGBoost MW | +0.003009 | +0.003383 | +0.000374 |

In random CV, clipped XGBoost M0/ME/MW RMSEs are **0.320457/0.311803/0.311983**; the respective buffered values are **0.320457/0.311434/0.312055**. The clipped walking–Euclidean RMSE gap is only **+0.000180** randomly, versus **+0.001543** geographically (positive means walking has higher error). In geographic validation the buffered gaps were +0.001814 for XGBoost and +0.002772 for OLS; after clipping they are +0.001543 and +0.002961. Thus neither the Euclidean-versus-walking ordering nor the random/geographic validation contrast reverses. This is not a claim of a statistically decisive ranking; folds are correlated and differences are small.

The [paired 11-area table](../outputs/tables/boundary_sensitivity_geographic_pairs.csv) shows clipped XGBoost ME and MW still beat M0 in **7/11 areas each**, the same counts as buffered. Changes are not uniform: the small Brønshøj-Husum fold (N=221) gains +0.00563 more ME improvement and +0.00369 more MW improvement after clipping, whereas Bispebjerg's ME improvement declines by 0.00370. This variation is why the pooled changes should not be interpreted as a universal edge effect. Frederiksberg remains a municipality-sized held-out proxy with an unseen municipality category in training.

## Answers and disposition

1. **Outside destinations:** 691 food/social, 191 cultural/tourist and 78 selected stations.
2. **Changed listing values:** 1,467/883 food E/W counts, 1,155/382 cultural E/W counts and 74/80 nearest-station E/W values, all on the 12,412 common sample.
3. **Euclidean incremental value:** essentially unchanged geographically; XGBoost gain shifts +0.004824→+0.004926 and OLS +0.006700→+0.006775.
4. **Walking incremental value:** essentially unchanged geographically; XGBoost gain shifts +0.003009→+0.003383 and OLS +0.003928→+0.003814. Individual folds vary more than these pooled shifts.
5. **Ordering:** Euclidean remains lower-error than walking for geographic OLS/XGBoost. The gap narrows modestly for geographic XGBoost but does not reverse.
6. **Location:** changed values are overwhelmingly within 800 m of the outer union edge; the coastline and polygon geometry are included in that boundary.
7. **Primary definition:** the results support retaining the buffered opportunity universe, which avoids making an administrative line an artificial opportunity wall. The clipped variant remains an explicitly labelled secondary sensitivity. This check does not undo the separate context-adjusted qualification of Phase 9's incremental access claims.

## Files and safeguards

Use `make boundary-audit` for the pre-fit endpoint/feature audit, `make boundary-models` for the fixed model set, and `make boundary-test` for read-only integrity checks. Aggregate CSVs are `outputs/tables/boundary_sensitivity_{destination_counts,feature_changes,performance,fold_performance,comparison}.csv`, plus `boundary_sensitivity_geographic_pairs.csv`, `boundary_sensitivity_edge_concentration.csv`, tuning and metadata. No public table contains listing IDs, names, text or point coordinates. The Phase 9 artifact/CV-assignment hash guard ran before and after fitting; all three live boundary-integrity tests passed. The archive is from September, later than June listing prices; listed DKK prices are not transactions. No Phase 9 result, model selection, threshold or raw input was replaced.

### Later presentation addendum — 2026-09-30

The original report judged an extra map unnecessary for the *inference*, and that remains true: the aggregate tables above are the evidence. At the user's later request, a separate [appendix catchment illustration](../outputs/figures/final/appendix_boundary_catchment_example.png) was created to make endpoint eligibility visually clear. It uses a public OSM node beside Hellerup station and shows 22 nearby canonical POIs under the buffered universe versus 4 retained inside/on the study union. It is not a new listing-level feature, route result or model; main-text Figure 4 and all frozen outputs remain unchanged. See [illustration provenance](appendix_boundary_catchment_figure.md).
