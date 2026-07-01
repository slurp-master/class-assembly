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
    regular_count = sum(1 for p in players if not p.is_backup)
    logger.info(f'Player summary: Total={len(players)}, Backup={backup_count}, '
                f'Regular={regular_count}')

    logger.info('Role availability:')
    for role in ROLES:
        count = sum(1 for p in players if role in p.available_roles)
        logger.info(f'  {role}: {count}')


def remove_emojis(text):
    """Remove emoji from text"""
    return ''.join(c for c in text if unicodedata.category(c)[0] != 'S')


def build_results_dataframe(groups, backup):
    """Build dataframe with group assignments and separators"""
    data = []
    for group_idx, group in enumerate(groups, 1):

        print(group.ordered_members())

        for member in group.ordered_members():
            clean_name = remove_emojis(member.global_name)
            row = {'group': group_idx, 'player': clean_name}
            for role in ROLES:
                row[role] = '✓' if role in member.available_roles else ''
            data.append(row)

        empty_row = {'group': '', 'player': ''}
        for role in ROLES:
            empty_row[role] = ''
        data.append(empty_row)

        separator = {'group': 'group', 'player': 'player'}
        for role in ROLES:
            separator[role] = role
        data.append(separator)

    for member in backup:
        clean_name = remove_emojis(member.global_name)
        row = {'group': 'B', 'player': clean_name}
        for role in ROLES:
            row[role] = '✓' if role in member.available_roles else ''
        data.append(row)

    return pd.DataFrame(data)


def print_results(groups, backup, df):
    """Print results table and summary"""
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    print('\n')
    print(df.to_string(index=False))
    logger.info(f'  Groups: {len(groups)}')
    logger.info(f'  Players in groups: {sum(len(g.members) for g in groups)}')
    logger.info(f'  Backup: {len(backup)}')
    logger.info(f'  Total: {sum(len(g.members) for g in groups) + len(backup)}')


def main(seed=None):
    players = load_players('data/010_reactions/reactions.csv')
    print_initial_stats(players)

    if seed is not None:
        logger.info(f'Using seed: {seed}')

    assembly = GroupAssembly(players, seed=seed)
    groups, backup = assembly.assemble_groups()

    logger.info('Balancing groups by experience (role flexibility)...')
    swaps = swap_members_for_balance(groups)
    logger.info(f'Completed {swaps} swaps')

    total_in_groups = sum(len(g.members) for g in groups)
    logger.info(f'Assembly Summary:')
    logger.info(f'  Groups: {len(groups)}')
    logger.info(f'  Players in groups: {total_in_groups}')
    logger.info(f'  Backup: {len(backup)}')
    logger.info(f'  Total: {total_in_groups + len(backup)}')

    export_groups_to_csv(groups, backup, 'data/020_setup/setup.csv')

    df = build_results_dataframe(groups, backup)
    log_group_balance(groups)
    print_results(groups, backup, df)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create raid group setup')
    parser.add_argument('--seed', type=int, default=None, help='Random seed for reproducibility')
    args = parser.parse_args()
    main(seed=args.seed)
