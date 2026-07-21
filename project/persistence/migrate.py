"""Run Intake persistence migrations with ``python -m persistence.migrate``."""

from persistence.database import migrate


if __name__ == "__main__":
    database = migrate()
    print(f"Intake migrations applied ({database.backend})")
