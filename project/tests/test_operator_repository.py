"""Repository tests for operator listing and activation."""

from persistence import Database, Persistence


def test_operator_list_all_and_set_active(tmp_path) -> None:
    store = Persistence(Database("", sqlite_path=tmp_path / "operators.db"))
    store.operators.ensure("alpha@example.com", display_name="Alpha")
    store.operators.ensure("beta@example.com", display_name="Beta")

    rows = store.operators.list_all()
    assert [row["email"] for row in rows] == [
        "alpha@example.com",
        "beta@example.com",
    ]

    assert store.operators.set_active("beta@example.com", False)
    refreshed = store.operators.get("beta@example.com")
    assert refreshed is not None
    assert not refreshed["active"]
