"""Grant the "members.manage" permission to existing system "Caregiver" roles.

DEFAULT_ROLES now gives the Caregiver role "members.manage", but families created
before that change already have a Caregiver Role row without it. This script adds
the missing RolePermission row to those roles and touches nothing else.

Run from carecircle/backend:

    python scripts/grant_caregiver_members_manage.py          # dry run (no writes)
    python scripts/grant_caregiver_members_manage.py --apply  # insert the missing rows

Idempotent: roles that already have "members.manage" are skipped.
"""

import argparse
import sys
from pathlib import Path

# Make the `app` package importable when run as `python scripts/<name>.py`
# from carecircle/backend (the script's own folder is on sys.path, not the backend).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.family import Family  # noqa: E402
from app.models.role import Role, RolePermission  # noqa: E402

ROLE_NAME = "Caregiver"
PERMISSION = "members.manage"


def find_roles_needing_change(db):
    """Return (role, family) pairs for system Caregiver roles lacking members.manage."""
    rows = db.execute(
        select(Role, Family)
        .join(Family, Family.id == Role.family_id)
        .where(Role.name == ROLE_NAME, Role.is_system.is_(True))
        .order_by(Family.name, Role.id)
    ).all()

    pending = []
    for role, family in rows:
        has_permission = db.execute(
            select(RolePermission.id).where(
                RolePermission.role_id == role.id,
                RolePermission.permission == PERMISSION,
            )
        ).first()
        if has_permission is None:
            pending.append((role, family))
    return pending


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the changes. Without this flag the script only reports them.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        pending = find_roles_needing_change(db)

        mode = "APPLY" if args.apply else "DRY RUN"
        print(f"[{mode}] System '{ROLE_NAME}' roles missing '{PERMISSION}':")
        for role, family in pending:
            print(f"  family_id={family.id}  family_name={family.name!r}  role_id={role.id}")

        if not args.apply:
            print(f"Would change {len(pending)} role(s). Re-run with --apply to write.")
            return 0

        try:
            for role, _family in pending:
                db.add(RolePermission(role_id=role.id, permission=PERMISSION))
            db.commit()
        except Exception:
            db.rollback()
            raise

        print(f"Changed {len(pending)} role(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
