import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

import backend.models  # noqa: F401 - register all ORM tables before create_all
from backend.database import Base
from backend.models.attachment import Attachment
from backend.models.engine import EngineEvent
from backend.models.fuel import FuelTransaction
from backend.models.production import ProductionRecord
from backend.models.project import Project
from backend.models.shift import Shift
from backend.models.shift_attachments import ShiftAttachment
from backend.models.site import Site
from backend.models.sounding import Sounding
from backend.models.transfer import FuelTransfer
from backend.models.transfer_attachment import TransferAttachment
from backend.models.user import User
from backend.models.vessel import Vessel


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


class ProjectAccessTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.project_a = Project(name="Project A", code="A", is_active=True)
        self.project_b = Project(name="Project B", code="B", is_active=True)
        self.db.add_all([self.project_a, self.project_b])
        self.db.flush()
        self.vessel_a = Vessel(project_id=self.project_a.id, name="Vessel A", is_active=True)
        self.vessel_b = Vessel(project_id=self.project_b.id, name="Vessel B", is_active=True)
        self.db.add_all([self.vessel_a, self.vessel_b])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_session_scope_filters_projects_and_vessels(self):
        project_a_id = self.project_a.id
        vessel_a_id = self.vessel_a.id
        vessel_b_id = self.vessel_b.id
        self.db.expunge_all()
        self.db.info["project_scope_user_id"] = 42
        self.db.info["project_scope_ids"] = [project_a_id]

        projects = self.db.scalars(select(Project).order_by(Project.id)).all()
        vessels = self.db.scalars(select(Vessel).order_by(Vessel.id)).all()

        self.assertEqual([project.id for project in projects], [project_a_id])
        self.assertEqual([vessel.id for vessel in vessels], [vessel_a_id])
        self.assertIsNone(self.db.get(Vessel, vessel_b_id))

    def test_empty_assignment_has_no_project_data(self):
        self.db.info["project_scope_user_id"] = 42
        self.db.info["project_scope_ids"] = []

        self.assertEqual(self.db.scalars(select(Project)).all(), [])
        self.assertEqual(self.db.scalars(select(Vessel)).all(), [])

    def test_related_record_filters_compile_for_project_scoped_sessions(self):
        self.db.info["project_scope_user_id"] = 42
        self.db.info["project_scope_ids"] = [self.project_a.id]
        for model in (
            Site,
            Shift,
            Sounding,
            FuelTransaction,
            EngineEvent,
            FuelTransfer,
            ProductionRecord,
            Attachment,
            ShiftAttachment,
            TransferAttachment,
        ):
            self.assertEqual(self.db.scalars(select(model)).all(), [])

    def test_user_project_assignments_persist(self):
        user = User(
            username="operator_a",
            password_hash="hash",
            role="OPERATOR",
            projects=[self.project_a],
        )
        self.db.add(user)
        self.db.commit()
        self.db.expire_all()

        saved = self.db.scalar(select(User).where(User.username == "operator_a"))
        self.assertEqual(saved.project_ids, [self.project_a.id])


if __name__ == "__main__":
    unittest.main()
