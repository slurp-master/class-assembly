from typing import List, Dict
from lib.grouper import Group
from lib.logging_setup import setup_logging

logger = setup_logging(__name__)


def calculate_group_experience(group: Group) -> int:
    """Calculate total experience of a group (sum of player experiences)"""
    return sum(member.experience for member in group.members)


def calculate_group_imbalance(groups: List[Group]) -> float:
    """Calculate imbalance metric (std deviation of group experiences)"""
    if not groups:
        return 0.0

    experiences = [calculate_group_experience(g) for g in groups]
    mean = sum(experiences) / len(experiences)
    variance = sum((x - mean) ** 2 for x in experiences) / len(experiences)
    return variance ** 0.5


def swap_members_for_balance(groups: List[Group], max_iterations: int = 100) -> int:
    """Iteratively swap members between groups to improve balance"""
    improved = 0

    for iteration in range(max_iterations):
        initial_imbalance = calculate_group_imbalance(groups)
        best_swap = None
        best_imbalance = initial_imbalance

        for i, group1 in enumerate(groups):
            for j, group2 in enumerate(groups):
                if i >= j:
                    continue

                for member1 in group1.members:
                    for member2 in group2.members:
                        if member1.available_roles == member2.available_roles:
                            continue

                        try:
                            group1.members.remove(member1)
                            group1.members.append(member2)
                            group2.members.remove(member2)
                            group2.members.append(member1)

                            new_imbalance = calculate_group_imbalance(groups)

                            if new_imbalance < best_imbalance:
                                best_imbalance = new_imbalance
                                best_swap = (i, j, member1, member2)

                            group1.members.remove(member2)
                            group1.members.append(member1)
                            group2.members.remove(member1)
                            group2.members.append(member2)
                        except ValueError:
                            pass

        if best_swap:
            i, j, member1, member2 = best_swap
            groups[i].members.remove(member1)
            groups[i].members.append(member2)
            groups[j].members.remove(member2)
            groups[j].members.append(member1)
            improved += 1
            logger.info(f'Iteration {iteration + 1}: Swapped {member1.global_name} '
                        f'({len(member1.available_roles)} roles) with '
                        f'{member2.global_name} ({len(member2.available_roles)} roles), '
                        f'imbalance: {best_imbalance:.2f}')
        else:
            logger.info(f'No improvement found at iteration {iteration + 1}, stopping')
            break

    final_imbalance = calculate_group_imbalance(groups)
    logger.info(f'Final imbalance: {final_imbalance:.2f}')
    return improved


def log_group_balance(groups: List[Group]):
    """Log balance statistics for groups"""
    experiences = [calculate_group_experience(g) for g in groups]
    min_exp = min(experiences)
    max_exp = max(experiences)
    mean_exp = sum(experiences) / len(experiences)
    imbalance = calculate_group_imbalance(groups)

    logger.info(f'Group Balance Statistics:')
    logger.info(f'  Min experience: {min_exp}')
    logger.info(f'  Max experience: {max_exp}')
    logger.info(f'  Mean experience: {mean_exp:.1f}')
    logger.info(f'  Imbalance (std dev): {imbalance:.2f}')
    logger.info(f'Experiences by group:')
    for i, exp in enumerate(experiences, 1):
        logger.info(f'  Group {i}: {exp}')
