"""Test helpers: fake 512-d embeddings with exact known cosine similarities."""

from __future__ import annotations

import math

import numpy as np
import pytest


def unit(i: int) -> np.ndarray:
    """i-th standard basis vector in R^512 (unit norm)."""
    v = np.zeros(512, dtype=np.float32)
    v[i] = 1.0
    return v


def vec_with_sim(base: np.ndarray, sim: float, perp_index: int) -> np.ndarray:
    """A unit vector whose cosine similarity to `base` is exactly `sim`.
    `perp_index` selects an axis orthogonal to base."""
    perp = unit(perp_index)
    assert abs(float(np.dot(base, perp))) < 1e-9
    return (sim * base + math.sqrt(1.0 - sim * sim) * perp).astype(np.float32)


@pytest.fixture
def helpers():
    class H:
        unit = staticmethod(unit)
        vec_with_sim = staticmethod(vec_with_sim)

    return H
