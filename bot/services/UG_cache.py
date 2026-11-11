"""Compatibility imports for the shared user/group cache records.

The implementation moved to ``shared.runtime`` so bot handlers and server
services can use one cache contract. Existing imports keep working.
"""
from shared.runtime import (
    Agroup,
    Auser,
    GroupsRecord,
    UsersRecord,
    load_groups,
    load_users,
)

__all__ = [
    "Agroup",
    "Auser",
    "GroupsRecord",
    "UsersRecord",
    "load_groups",
    "load_users",
]