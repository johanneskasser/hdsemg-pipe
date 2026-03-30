"""
HD-sEMG Motor Unit Study - Database Initialization Script

Creates a new SQLite database with the full schema.
Safe to run on an existing DB (uses IF NOT EXISTS throughout).

Usage:
    python db_setup/init_db.py
    python db_setup/init_db.py --db-path /path/to/mu_study.db
    python db_setup/init_db.py --db-path mu_study.db --verify
"""
import argparse
import sys
from pathlib import Path

# Allow running from project root or from db_setup/
sys.path.insert(0, str(Path(__file__).parent))

from db_connector import DatabaseConnection


def init_db(db_path: str, verify: bool = False) -> None:
    """
    Initialize the database at the given path.

    Args:
        db_path: Path to .db file (created if it doesn't exist)
        verify: If True, run a quick schema check after init
    """
    db_path = Path(db_path)

    print(f"Initializing database: {db_path.resolve()}")

    with DatabaseConnection(str(db_path)) as db:
        db.init_schema()

        if verify:
            _verify_schema(db)


def _verify_schema(db: DatabaseConnection) -> None:
    """Quick check that all expected tables and views exist."""
    expected_tables = [
        "subjects", "sessions", "recordings",
        "motor_units", "tracking_clusters", "mu_tracking",
    ]
    expected_views = [
        "v_mu_full", "v_mu_tracked_4block", "v_mu_tracked_6block",
        "v_recording_summary", "v_tracking_summary", "v_mu_crossover",
    ]

    df_tables = db.query(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    df_views = db.query(
        "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
    )

    existing_tables = set(df_tables["name"].tolist())
    existing_views = set(df_views["name"].tolist())

    print("\n--- Schema Verification ---")
    all_ok = True

    for table in expected_tables:
        ok = table in existing_tables
        symbol = "✓" if ok else "✗"
        print(f"  {symbol} Table: {table}")
        if not ok:
            all_ok = False

    for view in expected_views:
        ok = view in existing_views
        symbol = "✓" if ok else "✗"
        print(f"  {symbol} View:  {view}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n✓ All tables and views created successfully.")
        print("  Connect with DBeaver: Database > New Connection > SQLite")
        print(f"  Path: {db.db_path.resolve()}\n")
    else:
        print("\n✗ Schema verification failed - check error messages above.\n")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Initialize the HD-sEMG motor unit study SQLite database."
    )
    parser.add_argument(
        "--db-path",
        default="mu_study.db",
        help="Path to the database file (default: mu_study.db in current directory)"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run schema verification after initialization"
    )
    args = parser.parse_args()

    init_db(args.db_path, verify=args.verify)


if __name__ == "__main__":
    main()
