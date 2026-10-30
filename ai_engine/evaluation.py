"""Ranking metrics for the matching evaluation. Pure Python."""


def precision_at_k(ranked, relevant, k=5):
    """Share of the top k results that are relevant. Fixed denominator k."""
    if k <= 0:
        raise ValueError("k must be positive.")
    relevant = set(relevant)
    return sum(1 for item in list(ranked)[:k] if item in relevant) / k


def reciprocal_rank(ranked, relevant):
    """1 / rank of the first relevant result, or 0 if none appears.

    Useful when only a few listings are relevant, where precision@k is capped.
    """
    relevant = set(relevant)
    for position, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1 / position
    return 0.0


def recall_at_k(ranked, relevant, k=5):
    """Share of all relevant items that appear in the top k."""
    relevant = set(relevant)
    if not relevant:
        return 0.0
    return sum(1 for item in list(ranked)[:k] if item in relevant) / len(relevant)
