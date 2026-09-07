"""Vector encoding and similarity search.

Embeddings are stored as raw float32 bytes, which is compact, exact, and
portable: the same bytes load into numpy on SQLite and into a `vector` column
on Postgres. Search is brute-force cosine over a pre-filtered candidate set.

Brute force is the right call at this scale and it is worth being explicit
about why. A sales org's entire call history is tens of thousands of moments;
a 20k x 1024 float32 matrix is 80 MB and numpy scores it in single-digit
milliseconds. An approximate index would add operational weight and recall loss
to solve a problem nobody here has. `search()` is the seam -- swapping in
pgvector's `<=>` operator for the deploy path changes this function and nothing
else.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

DTYPE = np.float32


def encode(vector: Sequence[float]) -> bytes:
    return np.asarray(vector, dtype=DTYPE).tobytes()


def decode(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=DTYPE)


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def matrix(blobs: Iterable[bytes]) -> np.ndarray:
    """Stack stored embeddings into one matrix for a single BLAS call."""
    rows = [decode(b) for b in blobs]
    if not rows:
        return np.zeros((0, 0), dtype=DTYPE)
    width = len(rows[0])
    if any(len(r) != width for r in rows):
        raise ValueError(
            "embedding dimensions differ across rows -- the index was written "
            "by more than one model; re-embed before searching"
        )
    return np.vstack(rows)


def cosine_scores(query: Sequence[float], blobs: Sequence[bytes]) -> np.ndarray:
    """Cosine similarity of `query` against every stored vector.

    Both sides are normalised here rather than trusted, so a provider that
    returns unnormalised embeddings cannot quietly skew the ranking.
    """
    if not blobs:
        return np.zeros((0,), dtype=DTYPE)

    bank = matrix(blobs)
    q = normalize(np.asarray(query, dtype=DTYPE))
    if bank.shape[1] != q.shape[0]:
        raise ValueError(
            f"query dimension {q.shape[0]} does not match index {bank.shape[1]}"
        )

    norms = np.linalg.norm(bank, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (bank / norms) @ q


def top_k(
    query: Sequence[float],
    blobs: Sequence[bytes],
    k: int = 8,
    min_score: float = 0.0,
) -> list[tuple[int, float]]:
    """Indices and scores of the k closest vectors, best first."""
    scores = cosine_scores(query, blobs)
    if scores.size == 0:
        return []

    k = min(k, scores.size)
    # argpartition finds the top k without sorting the whole array.
    candidates = np.argpartition(-scores, k - 1)[:k]
    ranked = sorted(candidates, key=lambda i: -scores[i])
    return [(int(i), float(scores[i])) for i in ranked if scores[i] >= min_score]


def mmr(
    query: Sequence[float],
    blobs: Sequence[bytes],
    k: int = 5,
    diversity: float = 0.35,
    pool: int = 30,
) -> list[tuple[int, float]]:
    """Maximal Marginal Relevance selection.

    Plain top-k retrieval over a call archive returns five paraphrases of the
    same moment, because a rep who is good at something is good at it
    repeatedly. MMR trades a little relevance for coverage, so the Coach sees
    five *different* ways the objection was handled instead of one, five times.
    """
    scores = cosine_scores(query, blobs)
    if scores.size == 0:
        return []

    pool = min(pool, scores.size)
    candidates = list(np.argsort(-scores)[:pool])
    bank = matrix([blobs[i] for i in candidates])
    norms = np.linalg.norm(bank, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    bank = bank / norms

    selected: list[int] = []
    chosen_rows: list[np.ndarray] = []

    while candidates and len(selected) < k:
        best_i = None
        best_value = -np.inf
        for position, index in enumerate(candidates):
            relevance = float(scores[index])
            if chosen_rows:
                redundancy = max(
                    float(np.dot(bank[position], row)) for row in chosen_rows
                )
            else:
                redundancy = 0.0
            value = (1 - diversity) * relevance - diversity * redundancy
            if value > best_value:
                best_value, best_i = value, position

        if best_i is None:
            break
        index = candidates.pop(best_i)
        chosen_rows.append(bank[best_i])
        bank = np.delete(bank, best_i, axis=0)
        selected.append(index)

    return [(int(i), float(scores[i])) for i in selected]
