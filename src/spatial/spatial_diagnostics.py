"""Reproducible coordinate-only spatial diagnostics; EPSG:25832 metres."""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


def knn_indices(coordinates: np.ndarray, k: int = 8) -> np.ndarray:
    """Directed k-nearest-neighbour indices, excluding the focal row even at ties."""
    points = np.asarray(coordinates, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) <= k:
        raise ValueError("Expected more than k projected two-dimensional points")
    if not np.isfinite(points).all():
        raise ValueError("Spatial coordinates must be finite")
    _, candidates = cKDTree(points).query(points, k=min(len(points), k + 2))
    neighbours = np.empty((len(points), k), dtype=np.int64)
    for row, indices in enumerate(candidates):
        without_self = indices[indices != row]
        if len(without_self) < k:
            raise ValueError("Could not find k distinct neighbour records")
        neighbours[row] = without_self[:k]
    return neighbours


def moran_knn(values: np.ndarray, coordinates: np.ndarray, *, k: int = 8,
              permutations: int = 499, seed: int = 20260929) -> dict:
    """Moran's I with row-standardised directed kNN and two-sided permutation p."""
    y = np.asarray(values, dtype=float)
    if len(y) != len(coordinates) or not np.isfinite(y).all() or np.var(y) <= 0:
        raise ValueError("Moran values must be complete and variable")
    neighbours = knn_indices(coordinates, k)
    z = y - y.mean()
    denominator = np.dot(z, z)

    def statistic(vector: np.ndarray) -> float:
        # S0=N because every row's k directed weights sum to one.
        return float(np.dot(vector, vector[neighbours].mean(axis=1)) / denominator)

    observed = statistic(z)
    rng = np.random.default_rng(seed)
    null = np.fromiter((statistic(rng.permutation(z)) for _ in range(permutations)),
                       dtype=float, count=permutations)
    centre = float(null.mean())
    p_two_sided = (1 + int(np.count_nonzero(np.abs(null - centre) >= abs(observed - centre)))) / (
        permutations + 1
    )
    return {"n": len(y), "moran_i": observed, "expected_i": -1 / (len(y) - 1),
            "permutation_mean": centre, "permutation_p_two_sided": p_two_sided,
            "k": k, "directed_edges": len(y) * k, "permutations": permutations,
            "seed": seed, "crs_epsg": 25832}


def distance_bin_covariance(values: np.ndarray, coordinates: np.ndarray, *,
                            edges_m: tuple[int, ...] = (0, 250, 500, 1000, 2000, 4000, 8000),
                            pair_draws: int = 600_000, seed: int = 20260930) -> list[dict]:
    """Sampled, standardized cross-products by distance; not a formal variogram."""
    y = np.asarray(values, dtype=float)
    points = np.asarray(coordinates, dtype=float)
    if len(y) != len(points) or not np.isfinite(y).all() or np.var(y) <= 0:
        raise ValueError("Spatial covariance values must be complete and variable")
    rng = np.random.default_rng(seed)
    left = rng.integers(0, len(y), size=pair_draws)
    right = rng.integers(0, len(y), size=pair_draws)
    distinct = left != right
    left, right = left[distinct], right[distinct]
    distance = np.linalg.norm(points[left] - points[right], axis=1)
    z = (y - y.mean()) / y.std()
    product = z[left] * z[right]
    return [{"lower_m": lower, "upper_m": upper, "sampled_pairs": int(mask.sum()),
             "mean_standardized_cross_product": float(product[mask].mean()) if mask.any() else None,
             "pair_draws": pair_draws, "seed": seed, "crs_epsg": 25832}
            for lower, upper in zip(edges_m[:-1], edges_m[1:])
            for mask in [(distance >= lower) & (distance < upper)]]
