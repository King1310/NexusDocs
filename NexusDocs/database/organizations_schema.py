from pathlib import Path

from database.organization_database_manager import OrganizationDatabaseManager


def create_organizations_tables(database_file: Path | None = None) -> None:
    db = OrganizationDatabaseManager(database_file)
    db.connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS territories
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT NOT NULL,
            district TEXT NOT NULL DEFAULT '',
            city TEXT NOT NULL DEFAULT '',
            locality TEXT NOT NULL DEFAULT '',
            street TEXT NOT NULL DEFAULT '',
            UNIQUE(region, district, city, locality, street)
        );

        CREATE TABLE IF NOT EXISTS organizations
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_type TEXT NOT NULL,
            recipient TEXT NOT NULL,
            postal_address TEXT NOT NULL,
            phones TEXT NOT NULL DEFAULT '[]',
            email TEXT NOT NULL DEFAULT '',
            fax TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            verification_status TEXT NOT NULL DEFAULT 'unverified',
            verified_at TEXT NOT NULL DEFAULT '',
            verification_note TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS territory_organizations
        (
            territory_id INTEGER NOT NULL,
            organization_type TEXT NOT NULL,
            organization_id INTEGER NOT NULL,
            PRIMARY KEY (territory_id, organization_type),
            FOREIGN KEY (territory_id) REFERENCES territories(id) ON DELETE CASCADE,
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        );
        """
    )

    columns = {
        row["name"]
        for row in db.connection.execute("PRAGMA table_info(organizations)")
    }
    if "verified_at" not in columns:
        db.connection.execute(
            "ALTER TABLE organizations "
            "ADD COLUMN verified_at TEXT NOT NULL DEFAULT ''"
        )
    if "verification_note" not in columns:
        db.connection.execute(
            "ALTER TABLE organizations "
            "ADD COLUMN verification_note TEXT NOT NULL DEFAULT ''"
        )
    db.connection.commit()
