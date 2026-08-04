from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.db.session import engine, SessionLocal
from app.models.tables import Base, Project, ProjectAssignment, User


def seed_demo_data() -> None:
    # Ensure the schema exists for convenience; production should use Alembic migrations.
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        demo_user = User(
            email="demo.user@company.com",
            name="Demo User",
            role="employee",
            created_at=datetime.now(timezone.utc),
        )
        admin_user = User(
            email="admin.user@company.com",
            name="Admin User",
            role="admin",
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([demo_user, admin_user])
        session.commit()

        project = Project(
            name="Demo Project",
            aliases=["demo", "project-demo"],
            client_name="Demo Client",
            date_range_start=datetime.utcnow(),
            date_range_end=None,
            created_by=admin_user.id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(project)
        session.commit()

        assignment = ProjectAssignment(
            project_id=project.id,
            user_id=demo_user.id,
            assigned_by=admin_user.id,
            assigned_at=datetime.now(timezone.utc),
        )
        session.add(assignment)
        session.commit()

        print(f"Seeded demo project {project.id} and users {demo_user.id}, {admin_user.id}")


if __name__ == "__main__":
    seed_demo_data()
