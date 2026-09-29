1. Never modify raw source files in place. Raw data are immutable.

2. PostgreSQL/PostGIS is the authoritative persistent analytical data layer.
   Intermediate CSVs may be created for inspection/export, but should not
   become alternative undocumented sources of truth.

3. Never silently fill missing data.

4. Never statistically impute the outcome variable `price_nightly` or `log_price`.

5. Any learned preprocessing, imputation, feature selection, or tuning used
   for predictive evaluation must be fitted using training data only.

6. Never use the outer test fold to choose hyperparameters, accessibility
   thresholds, POI categories, variables, or preprocessing decisions.

7. All spatial operations must record the CRS used.

8. All externally acquired data must record source, acquisition date,
   geographic extent, and—where possible—a file checksum.

9. Do not fabricate geographic mappings, neighbourhoods, variables, or values
   when required data are unavailable.

10. Do not add new modelling techniques solely because they improve headline
    performance. Deviations from the pre-analysis specification must be logged.

11. Prefer reusable scripts/functions and SQL migrations over manual notebook
    operations.

12. Every analysis table and figure must be reproducible from code.