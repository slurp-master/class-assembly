import pandas as pd

from lib.loader import load_players


def write_csv(tmp_path, rows):
    path = tmp_path / 'reactions.csv'
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def base_row(**overrides):
    row = {
        'username': 'alice', 'global_name': 'Alice', 'check': True,
        'tank': False, 'pure': False, 'shield': False,
        'caster': False, 'melee': False, 'ranged': False,
        'backup': False, 'raid_leader': False,
    }
    row.update(overrides)
    return row


class TestLoadPlayers:
    def test_it_loads_only_real_roles_into_available_roles(self, tmp_path):
        path = write_csv(tmp_path, [base_row(tank=True, melee=True)])
        subject = load_players(path)[0]
        assert subject.available_roles == frozenset({'tank', 'melee'})

    def test_it_does_not_treat_check_in_as_a_role(self, tmp_path):
        # 'check' is True for everyone; it must not inflate roles or become playable.
        path = write_csv(tmp_path, [base_row(check=True, tank=True)])
        subject = load_players(path)[0]
        assert 'check' not in subject.available_roles
        assert not subject.can('check')
        assert subject.num_roles == 1        # tank only, not tank + check

    def test_it_reads_the_backup_flag(self, tmp_path):
        path = write_csv(tmp_path, [base_row(tank=True, backup=True)])
        subject = load_players(path)[0]
        assert subject.is_backup

    def test_it_reads_the_raid_leader_flag(self, tmp_path):
        path = write_csv(tmp_path, [base_row(tank=True, raid_leader=True)])
        subject = load_players(path)[0]
        assert subject.is_raid_leader

    def test_it_loads_a_player_with_no_roles_as_empty(self, tmp_path):
        path = write_csv(tmp_path, [base_row()])
        subject = load_players(path)[0]
        assert subject.available_roles == frozenset()
        assert subject.num_roles == 0
