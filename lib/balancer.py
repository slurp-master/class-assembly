from typing import List, Optional, Tuple
from lib.models import Group, Assignment
from lib.logging_setup import setup_logging

logger = setup_logging(__name__)


def _imbalance(experiences: List[int]) -> float:
    """Std deviation of a list of group experience totals."""
    if not experiences:
        return 0.0
    mean = sum(experiences) / len(experiences)
    variance = sum((x - mean) ** 2 for x in experiences) / len(experiences)
    return variance ** 0.5


def calculate_group_imbalance(groups: List[Group]) -> float:
    """Calculate imbalance metric (std deviation of group experiences)"""
    return _imbalance([g.experience for g in groups])


def swap_members_for_balance(groups: List[Group], max_iterations: int = 100) -> int:
    """Iteratively swap members between groups to improve experience balance.

    Only composition-preserving swaps are considered: two players are exchanged and
    each takes over the other's assigned role slot, which is valid only when both can
    play the other's role (see Assignment.can_swap_with). Swaps that would strip a group
    of its required raid leader are also rejected. This keeps every group's fixed role
    composition and raid-leader requirement intact.
    """
    improved = 0

    for iteration in range(max_iterations):
        experiences = [g.experience for g in groups]
        best_imbalance = _imbalance(experiences)
        best_swap: Optional[Tuple[Group, Assignment, Group, Assignment]] = None

        for i, group1 in enumerate(groups):
            for j, group2 in enumerate(groups[i + 1:], start=i + 1):
                for a in group1.assignments:
                    for b in group2.assignments:
                        if not a.can_swap_with(b):
                            continue
                        if not group1.swap_keeps_raid_leader(a, b.player):
                            continue
                        if not group2.swap_keeps_raid_leader(b, a.player):
                            continue

                        # A swap only moves a.experience and b.experience between the two
                        # groups; evaluate the resulting imbalance arithmetically rather
                        # than mutating and reverting the groups.
                        delta = b.experience - a.experience
                        trial = list(experiences)
                        trial[i] = experiences[i] + delta
                        trial[j] = experiences[j] - delta
                        new_imbalance = _imbalance(trial)

                        if new_imbalance < best_imbalance:
                            best_imbalance = new_imbalance
                            best_swap = (group1, a, group2, b)

        if best_swap is None:
            logger.info(f'No improvement found at iteration {iteration + 1}, stopping')
            break

        group1, a, group2, b = best_swap
        group1.swap(a, group2, b)
        improved += 1
        logger.info(
            f'Iteration {iteration + 1}: Swapped {a.player.global_name} '
            f'({a.experience} exp) with {b.player.global_name} ({b.experience} exp), '
            f'imbalance: {best_imbalance:.2f}'
        )

    final_imbalance = calculate_group_imbalance(groups)
    logger.info(f'Final imbalance: {final_imbalance:.2f}')
    return improved


def log_group_balance(groups: List[Group]):
    """Log balance statistics for groups"""
    if not groups:
        logger.info('No groups to report balance for')
        return

    experiences = [g.experience for g in groups]
    mean_exp = sum(experiences) / len(experiences)

    logger.info('Group Balance Statistics:')
    logger.info(f'  Min experience: {min(experiences)}')
    logger.info(f'  Max experience: {max(experiences)}')
    logger.info(f'  Mean experience: {mean_exp:.1f}')
    logger.info(f'  Imbalance (std dev): {calculate_group_imbalance(groups):.2f}')
    logger.info('Experiences by group:')
    for i, exp in enumerate(experiences, 1):
        logger.info(f'  Group {i}: {exp}')
