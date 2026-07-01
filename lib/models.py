from dataclasses import dataclass


@dataclass(frozen=True)
class Player:
    username: str
    global_name: str
    available_roles: frozenset
    is_backup: bool

    @property
    def experience(self) -> int:
        return self.num_roles

    @property
    def num_roles(self) -> int:
        """Number of roles this player can fill (used for constrainedness)"""
        return len(self.available_roles)

    def can(self, role: str) -> bool:
        return role in self.available_roles

    def __lt__(self, other):
        """Define ordering for deterministic sorting"""
        return self.username < other.username
