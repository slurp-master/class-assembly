import pandas as pd
from typing import List
from lib.models import Group, Player
from lib.logging_setup import setup_logging

logger = setup_logging(__name__)

ROLE_COLUMNS = ['tank', 'pure', 'shield', 'melee', 'caster', 'ranged']


def export_groups_to_csv(groups: List[Group], backup: List[Player], output_path: str):
    """Export group assignments to CSV using a pandas dataframe.

    Emits role-availability flags so the setup can be imported into other systems.
    The group is a viable combination; players pick their actual role once formed, so
    no role is assigned in the output.
    """
    data = []

    for group_idx, group in enumerate(groups, 1):
        for assignment in group.ordered_members():
            member = assignment.player
            row = {
                'group_id': group_idx,
                'global_name': member.global_name,
                'raid_leader': member.is_raid_leader,
                'group_needs_rl': group.needs_raid_leader,
            }
            for role in ROLE_COLUMNS:
                row[role] = role in member.available_roles
            data.append(row)

    for member in backup:
        row = {
            'group_id': 'backup',
            'global_name': member.global_name,
            'raid_leader': member.is_raid_leader,
            'group_needs_rl': False,
        }
        for role in ROLE_COLUMNS:
            row[role] = role in member.available_roles
        data.append(row)

    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    logger.info(f'Exported {len(groups)} groups and {len(backup)} backup players to {output_path}')
