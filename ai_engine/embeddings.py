"""Embedding helpers. Pure Python.

Opportunity embeddings are computed offline and stored on Opportunity.embedding.
At request time only the visitor's profile text is embedded, through a hosted
API (added when the provider is chosen), and compared with cosine similarity.
matching.rank_opportunities accepts the result as `similarities`.
"""
import math


def cosine_similarity(a, b):
    """Cosine similarity of two equal-length vectors, in [-1, 1]. Zero vectors give 0."""
    if len(a) != len(b):
        raise ValueError("Vectors must have the same length.")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def similarities_for(profile_vector, opportunities):
    """Map opportunity pk to similarity, skipping listings with no stored embedding."""
    out = {}
    for opp in opportunities:
        vector = getattr(opp, "embedding", None)
        if vector:
            out[opp.pk] = cosine_similarity(profile_vector, vector)
    return out
