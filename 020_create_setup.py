import argparse
import pandas as pd
import unicodedata
from lib.loader import load_players
from lib.grouper import GroupAssembly
from lib.exporter import export_groups_to_csv
from lib.balancer import swap_members_for_balance, log_group_balance
from lib.logging_setup import setup_logging

logger = setup_logging(__name__)

ROLES = ['tank', 'pure', 'shield', 'melee', 'caster', 'ranged']


def print_initial_stats(players):
    """Print initial player statistics"""
    logger.info(f'Loaded {len(players)} players')

    backup_count = sum(1 for p in players if p.is_backup)
    regular_count = len(players) - backup_count
    rl_count = sum(1 for p in players if p.is_raid_leader)
    logger.info(f'Player summary: Total={len(players)}, Backup={backup_count}, Regular={regular_count}')
    logger.info(f'Raid leaders available: {rl_count}')

    logger.info('Role availability:')
    for role in ROLES:
        count = sum(1 for p in players if role in p.available_roles)
        logger.info(f'  {role}: {count}')


def remove_emojis(text):
    """Remove emoji from text"""
    return ''.join(c for c in text if unicodedata.category(c)[0] != 'S')


def _members_dataframe(members):
    """Dataframe of players (one row each) with a ✓ per role and a raid-leader marker."""
    rows = []
    for member in members:
        row = {'player': remove_emojis(member.global_name), 'RL': '★' if member.is_raid_leader else ''}
        for role in ROLES:
            row[role] = '✓' if role in member.available_roles else ''
        rows.append(row)
    return pd.DataFrame(rows)


def print_results(groups, backup):
    """Print each group as its own table, then the backup, then a summary."""
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)

    for group_idx, group in enumerate(groups, 1):
        members = [a.player for a in group.ordered_members()]
        df = _members_dataframe(members)
        rl_note = ' -- NEEDS RAID LEADER (phantom)' if group.needs_raid_leader else ''
        print(f'\nGroup {group_idx}{rl_note}')
        print(df.to_string(index=False))

    if backup:
        print('\nBackup')
        print(_members_dataframe(backup).to_string(index=False))

    total_in_groups = sum(len(g.members) for g in groups)
    logger.info('Assembly Summary:')
    logger.info(f'  Groups: {len(groups)}')
    logger.info(f'  Players in groups: {total_in_groups}')
    logger.info(f'  Backup: {len(backup)}')
    logger.info(f'  Total: {total_in_groups + len(backup)}')


def main(seed=None, phantom_rl=0):
    players = load_players('data/010_reactions/reactions.csv')
    print_initial_stats(players)

    if seed is not None:
        logger.info(f'Using seed: {seed}')

    assembly = GroupAssembly(players, seed=seed, phantom_rl=phantom_rl)
    groups, backup = assembly.assemble_groups()

    logger.info('Balancing groups by experience...')
    swaps = swap_members_for_balance(groups)
    logger.info(f'Completed {swaps} swaps')

    export_groups_to_csv(groups, backup, 'data/020_setup/setup.csv')

    log_group_balance(groups)
    print_results(groups, backup)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create raid group setup')
    parser.add_argument('--seed', type=int, default=None, help='Random seed for reproducibility')
    parser.add_argument('--phantom-rl', type=int, default=0,
                        help='Number of groups allowed to form without a real raid leader')
    args = parser.parse_args()
    main(seed=args.seed, phantom_rl=args.phantom_rl)
