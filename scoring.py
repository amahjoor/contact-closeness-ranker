"""Glicko-style scoring engine for relationship ranking.

Based on the Glicko rating system by Mark Glickman (1995).
Adapted for relationship closeness scoring with bucket floors
and time-based uncertainty decay.

Key differences from standard Glicko:
- Scores represent relationship closeness, not competitive skill
- Bucket assignment sets a floor on the score
- Uncertainty (RD) grows over time when a contact isn't compared,
  modeling the real-world drift in relationships (Roberts & Dunbar, 2015)
"""

import math
from datetime import datetime
from typing import Optional

from models import ContactState, Bucket, BUCKET_CONFIG

# Glicko constants
Q = math.log(10) / 400  # ~0.00575646

# Time decay constant. Calibrated so that after ~90 days of no comparisons,
# RD returns to near-bucket-assignment level (~200).
# Given RD_active ~50: sqrt(50^2 + c^2 * 90) = 200 => c ~= 20.4
C_DECAY = 20.4

# RD bounds
RD_MIN = 30.0    # very confident after many comparisons
RD_MAX = 350.0   # no information at all
RD_BUCKET = 200.0  # after bucket assignment, before any pairwise


def _g(rd: float) -> float:
    """Glicko g-function: reduces impact of opponents with high uncertainty."""
    return 1.0 / math.sqrt(1.0 + 3.0 * Q * Q * rd * rd / (math.pi * math.pi))


def _expected(score: float, opp_score: float, opp_rd: float) -> float:
    """Expected outcome (0-1) of a comparison given scores and opponent RD."""
    return 1.0 / (1.0 + 10.0 ** (-_g(opp_rd) * (score - opp_score) / 400.0))


def apply_time_decay(state: ContactState, now: Optional[datetime] = None) -> None:
    """Increase RD based on time since last comparison.
    Models the real finding that relationships drift without active maintenance.
    """
    if state.last_compared_at is None:
        return

    if now is None:
        now = datetime.now()

    last = datetime.fromisoformat(state.last_compared_at)
    days_elapsed = (now - last).total_seconds() / 86400.0

    if days_elapsed <= 0:
        return

    new_rd = math.sqrt(state.rd ** 2 + C_DECAY ** 2 * days_elapsed)
    state.rd = min(new_rd, RD_MAX)


def update_scores(
    winner_state: ContactState,
    loser_state: ContactState,
    is_draw: bool = False,
) -> None:
    """Update both contacts' scores after a pairwise comparison.

    Args:
        winner_state: The contact chosen as 'closer' (or either, if draw)
        loser_state: The other contact
        is_draw: True if the user said they're equal
    """
    now = datetime.now()

    # Apply time decay before updating
    apply_time_decay(winner_state, now)
    apply_time_decay(loser_state, now)

    # Outcome values
    s_winner = 0.5 if is_draw else 1.0
    s_loser = 0.5 if is_draw else 0.0

    # --- Update winner ---
    g_loser = _g(loser_state.rd)
    e_winner = _expected(winner_state.score, loser_state.score, loser_state.rd)
    d2_winner = 1.0 / (Q * Q * g_loser * g_loser * e_winner * (1.0 - e_winner))

    score_delta_w = Q / (1.0 / winner_state.rd ** 2 + 1.0 / d2_winner) * g_loser * (s_winner - e_winner)
    new_rd_w = math.sqrt(1.0 / (1.0 / winner_state.rd ** 2 + 1.0 / d2_winner))

    # --- Update loser ---
    g_winner = _g(winner_state.rd)
    e_loser = _expected(loser_state.score, winner_state.score, winner_state.rd)
    d2_loser = 1.0 / (Q * Q * g_winner * g_winner * e_loser * (1.0 - e_loser))

    score_delta_l = Q / (1.0 / loser_state.rd ** 2 + 1.0 / d2_loser) * g_winner * (s_loser - e_loser)
    new_rd_l = math.sqrt(1.0 / (1.0 / loser_state.rd ** 2 + 1.0 / d2_loser))

    # Apply updates with bucket floor clamping
    winner_floor = BUCKET_CONFIG[winner_state.bucket]["floor"]
    loser_floor = BUCKET_CONFIG[loser_state.bucket]["floor"]

    winner_state.score = max(winner_floor, winner_state.score + score_delta_w)
    loser_state.score = max(loser_floor, loser_state.score + score_delta_l)

    winner_state.rd = max(RD_MIN, min(RD_MAX, new_rd_w))
    loser_state.rd = max(RD_MIN, min(RD_MAX, new_rd_l))

    # Update metadata
    ts = now.isoformat()
    winner_state.last_compared_at = ts
    loser_state.last_compared_at = ts
    winner_state.comparison_count += 1
    loser_state.comparison_count += 1
