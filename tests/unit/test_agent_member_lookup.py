"""Tests proving agent fails closed for unknown member IDs."""

from __future__ import annotations

import pytest

from sut.agent import _load_members


def test_known_member_ids_are_loadable() -> None:
    members = _load_members()
    assert members
    for member_id, member in members.items():
        assert member["member_id"] == member_id


def test_unknown_member_raises_key_error() -> None:
    members = _load_members()
    with pytest.raises(KeyError, match="MBR-UNKNOWN"):
        _ = members["MBR-UNKNOWN"]


def test_no_member_data_returned_for_unknown_id() -> None:
    members = _load_members()
    result = members.get("MBR-DOES-NOT-EXIST")
    assert result is None


def test_unknown_member_id_does_not_fall_back_to_first_member() -> None:
    members = _load_members()
    first_member_id = next(iter(members))
    unknown_id = "MBR-NOTREAL"
    assert unknown_id not in members
    result = members.get(unknown_id)
    assert result is None
    assert result != members[first_member_id]
