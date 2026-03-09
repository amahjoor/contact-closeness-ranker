"""Adaptive pair selection for pairwise comparisons.

Instead of random pairs, selects the most informative comparison to show
the user. This minimizes total comparisons needed to produce stable scores.

Based on active learning for ranking (Jamieson & Nowak, UW):
- Prioritize contacts with highest uncertainty (RD)
- Among uncertain contacts, pick pairs with similar scores (most informative)
- Avoid pairs where the outcome is obvious (big score gap + low RD)
"""

import random
from typing import List, Optional, Tuple, Set

from models import ContactState, Bucket


def _information_gain(a: ContactState, b: ContactState) -> float:
    """Estimate how much we'd learn from comparing a and b.

    High info gain when:
    - Both have high RD (uncertain)
    - Scores are close (outcome is hard to predict)

    Low info gain when:
    - Both have low RD (already confident)
    - Scores are far apart (outcome is obvious)
    """
    avg_rd = (a.rd + b.rd) / 2.0
    score_gap = abs(a.score - b.score)

    # RD component: higher RD = more to learn. Normalize to 0-1 range.
    rd_factor = avg_rd / 350.0

    # Score gap component: closer scores = more to learn.
    # At gap=0 this is 1.0, decays toward 0 as gap increases.
    gap_factor = 1.0 / (1.0 + score_gap / 100.0)

    return rd_factor * gap_factor


def select_pair(
    states: List[ContactState],
    past_pairs: Set[Tuple[str, str]],
    max_candidates: int = 50,
) -> Optional[Tuple[ContactState, ContactState]]:
    """Select the most informative pair to compare next.

    Args:
        states: All contact states that have been bucketed
        past_pairs: Set of (id_a, id_b) tuples already compared (sorted ids)
        max_candidates: How many candidate pairs to evaluate

    Returns:
        Tuple of two ContactStates, or None if no good pairs remain
    """
    # Filter to only bucketed contacts
    eligible = [s for s in states if s.bucket != Bucket.UNASSIGNED]

    if len(eligible) < 2:
        return None

    # Sort by RD descending - most uncertain first
    eligible.sort(key=lambda s: s.rd, reverse=True)

    # Take top candidates by uncertainty
    pool_size = min(len(eligible), max_candidates)
    pool = eligible[:pool_size]

    best_pair = None
    best_gain = -1.0

    # Evaluate candidate pairs from the pool
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            a, b = pool[i], pool[j]

            # Create sorted pair key for dedup
            pair_key = tuple(sorted([a.contact_id, b.contact_id]))

            # Prefer pairs that haven't been compared before,
            # but allow re-comparisons for contacts with high RD
            # (relationship may have changed)
            seen_before = pair_key in past_pairs
            if seen_before:
                # Only re-compare if both have high uncertainty
                if a.rd < 150 and b.rd < 150:
                    continue

            gain = _information_gain(a, b)

            # Slight penalty for re-comparisons
            if seen_before:
                gain *= 0.5

            # Small random jitter to avoid always showing the same pair
            gain += random.random() * 0.01

            if gain > best_gain:
                best_gain = gain
                best_pair = (a, b)

    return best_pair
