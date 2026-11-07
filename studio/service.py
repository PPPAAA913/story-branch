from uuid import uuid4

from .generation import GenerationError


class InputError(Exception):
    pass


class NotFoundError(Exception):
    pass


class UnsupportedActionError(Exception):
    pass


def validate_brief(raw):
    if not isinstance(raw, dict):
        raise InputError("The creative brief must be an object.")
    limits = {
        "market": 100,
        "language": 60,
        "genre": 80,
        "audience": 150,
        "premise": 1000,
        "production_limit": 300,
    }
    clean = {}
    for field, limit in limits.items():
        value = raw.get(field, "")
        if not isinstance(value, str):
            raise InputError(f"{field} must be text.")
        value = value.strip()
        if field != "production_limit" and not value:
            raise InputError(f"{field} is required.")
        if len(value) > limit:
            raise InputError(f"{field} is too long (max {limit} characters).")
        clean[field] = value
    return clean


class StudioService:
    def __init__(self, database, generator):
        self.database = database
        self.generator = generator

    def dispatch(self, payload):
        if not isinstance(payload, dict):
            raise InputError("Request body must be a JSON object.")
        action = payload.get("action")
        if action == "create":
            return self.create(payload.get("brief"))
        if action == "revise":
            return self.revise(payload.get("project_id"), payload.get("instruction"))
        if action == "outline":
            return self.build_outline(payload.get("project_id"), payload.get("concept_id"))
        raise UnsupportedActionError(f"Unsupported action: {action!r}.")

    def create(self, raw_brief):
        brief = validate_brief(raw_brief)
        project_id = uuid4().hex[:12]
        try:
            concepts = self.generator.generate_concepts(brief)
            self.database.create_project(project_id, brief, concepts)
            self.database.log_run(project_id, "create", "ok", self.generator.name)
        except GenerationError as exc:
            self.database.log_run(project_id, "create", "error", self.generator.name, str(exc))
            raise
        return self.get_project(project_id)

    def revise(self, project_id, instruction):
        project = self._require_project(project_id)
        if not isinstance(instruction, str) or not instruction.strip():
            raise InputError("A revision instruction is required.")
        if len(instruction) > 500:
            raise InputError("The revision instruction is too long (max 500 characters).")
        try:
            concepts = self.generator.generate_concepts(project["brief"], instruction.strip())
            self.database.update_project(project_id, concepts=concepts, clear_outline=True)
            self.database.log_run(project_id, "revise", "ok", self.generator.name)
        except GenerationError as exc:
            self.database.log_run(project_id, "revise", "error", self.generator.name, str(exc))
            raise
        return self.get_project(project_id)

    def build_outline(self, project_id, concept_id):
        project = self._require_project(project_id)
        concept = next((c for c in project["concepts"] if c["id"] == concept_id), None)
        if concept is None:
            raise InputError("Choose a concept from this project.")
        try:
            outline = self.generator.generate_outline(project["brief"], concept)
            self.database.update_project(project_id, selected_concept_id=concept_id, outline=outline)
            self.database.log_run(project_id, "outline", "ok", self.generator.name)
        except GenerationError as exc:
            self.database.log_run(project_id, "outline", "error", self.generator.name, str(exc))
            raise
        return self.get_project(project_id)

    def get_project(self, project_id):
        project = self._require_project(project_id)
        project["runs"] = self.database.list_runs(project_id)
        return project

    def _require_project(self, project_id):
        if not isinstance(project_id, str) or not project_id.strip():
            raise InputError("project_id is required.")
        project = self.database.get_project(project_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project
