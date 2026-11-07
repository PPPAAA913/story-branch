import tempfile
import unittest
from pathlib import Path

from studio.generation import DemoGenerator, GenerationError
from studio.service import InputError, StudioService, UnsupportedActionError
from studio.storage import Database


BRIEF = {
    "market": "English-speaking market",
    "language": "English",
    "genre": "Urban romance",
    "audience": "Young adult vertical-drama viewers",
    "premise": "A producer discovers an unexpected link to a rival",
    "production_limit": "Four main actors and two locations",
}


class BrokenGenerator(DemoGenerator):
    name = "broken-test"

    def generate_concepts(self, brief, revision_note=""):
        raise GenerationError("Forced model failure for the test.")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "studio.db")
        self.service = StudioService(self.db, DemoGenerator())

    def tearDown(self):
        self.temp.cleanup()

    def test_normal_input_and_later_read_of_saved_data(self):
        project = self.service.dispatch({"action": "create", "brief": BRIEF})
        self.assertEqual(3, len(project["concepts"]))
        selected = project["concepts"][1]["id"]
        outline = self.service.dispatch({"action": "outline", "project_id": project["id"], "concept_id": selected})
        self.assertEqual(selected, outline["selected_concept_id"])
        self.assertEqual(3, len(outline["outline"]["episodes"]))
        later_service = StudioService(Database(self.db.path), DemoGenerator())
        later = later_service.get_project(project["id"])
        self.assertEqual(outline["outline"], later["outline"])
        self.assertEqual(["create", "outline"], [run["action"] for run in later["runs"]])

    def test_invalid_input(self):
        incomplete = dict(BRIEF)
        del incomplete["language"]
        with self.assertRaisesRegex(InputError, "language is required"):
            self.service.dispatch({"action": "create", "brief": incomplete})

    def test_no_matching_action(self):
        with self.assertRaises(UnsupportedActionError):
            self.service.dispatch({"action": "unknown"})

    def test_forced_generation_error_is_logged(self):
        broken = StudioService(self.db, BrokenGenerator())
        with self.assertRaises(GenerationError):
            broken.dispatch({"action": "create", "brief": BRIEF})
        conn = self.db._connect()
        try:
            row = conn.execute("SELECT action, status, provider, error FROM runs").fetchone()
        finally:
            conn.close()
        self.assertEqual(("create", "error", "broken-test"), tuple(row)[:3])
        self.assertIn("Forced model failure", row["error"])

    def test_revision_clears_prior_outline(self):
        project = self.service.create(BRIEF)
        self.service.build_outline(project["id"], "c1")
        revised = self.service.revise(project["id"], "Fewer characters")
        self.assertIsNone(revised["outline"])
        self.assertIsNone(revised["selected_concept_id"])
        self.assertIn("Fewer characters", revised["concepts"][0]["logline"])


if __name__ == "__main__":
    unittest.main()
