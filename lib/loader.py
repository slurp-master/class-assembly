import pandas as pd
from typing import List
from lib.models import Player


def load_players(csv_path: str) -> List[Player]:
    """Load players from reactions.csv"""
    df = pd.read_csv(csv_path)

    players = []
    role_columns = ['check', 'tank', 'pure', 'shield', 'caster', 'melee', 'ranged', 'backup']

    for _, row in df.iterrows():
        available_roles = set()
        for role in role_columns:
            if role != 'backup' and pd.notna(row[role]) and row[role]:
                available_roles.add(role)

        is_backup = pd.notna(row.get('backup')) and row['backup']
        is_raid_leader = pd.notna(row.get('raid_leader')) and row['raid_leader']

        player = Player(
            username=row['username'],
            global_name=row['global_name'],
            available_roles=frozenset(available_roles),
            is_backup=is_backup,
            is_raid_leader=is_raid_leader,
        )
        players.append(player)

    return players
