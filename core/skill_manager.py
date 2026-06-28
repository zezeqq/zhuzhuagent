"""Legacy skills table access — prefer installed_skill_packages + skill_catalog."""

from db.database import query_all


def list_legacy_db_skills():
    """Rows from bootstrap `skills` table (built-in function paths, not SKILL.md packages)."""
    return query_all("SELECT * FROM skills ORDER BY id")
