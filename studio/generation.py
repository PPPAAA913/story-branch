import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GenerationError(Exception):
    pass


class DemoGenerator:
    name = "demo"

    def generate_concepts(self, brief, revision_note=""):
        premise = brief["premise"].rstrip(".。")
        genre = brief["genre"]
        audience = brief["audience"]
        note = f" Revision focus: {revision_note}." if revision_note else ""
        return [
            {
                "id": "c1", "title": "The Hidden Role",
                "logline": f"{premise}; a concealed identity turns the first alliance into a betrayal.{note}",
                "hook": "The protagonist recognizes someone who should be a stranger.",
                "core_conflict": "Trust must be earned before the secret becomes public.",
                "audience_fit": f"{genre} for {audience}, with a fast, relationship-led pace.",
            },
            {
                "id": "c2", "title": "The Reluctant Alliance",
                "logline": f"{premise}; two rivals must cooperate before a shared deadline.{note}",
                "hook": "The rivals receive the same impossible assignment.",
                "core_conflict": "Each needs the other while hiding a competing goal.",
                "audience_fit": f"{genre} for {audience}, with clear reversals and short scenes.",
            },
            {
                "id": "c3", "title": "One Public Choice",
                "logline": f"{premise}; one public decision threatens two private relationships.{note}",
                "hook": "A private promise is exposed in front of the wrong person.",
                "core_conflict": "The protagonist can protect a relationship or the truth, but not both.",
                "audience_fit": f"{genre} for {audience}, centered on an immediate emotional choice.",
            },
        ]

    def generate_outline(self, brief, concept):
        title = concept["title"]
        return {
            "series_title": title,
            "characters": [
                {"name": "Protagonist", "goal": "Protect the chosen relationship without losing agency."},
                {"name": "Counterpart", "goal": "Get the truth before the deadline."},
            ],
            "episodes": [
                {"number": 1, "opening": concept["hook"],
                 "turn": "The protagonist accepts a risky first step.",
                 "cliffhanger": "Evidence reveals the counterpart knows more than expected."},
                {"number": 2, "opening": "The alliance is tested by the new evidence.",
                 "turn": "A choice solves one problem and creates a larger one.",
                 "cliffhanger": "The hidden motive is exposed to a third person."},
                {"number": 3, "opening": "The public consequence arrives immediately.",
                 "turn": "The protagonist makes an irreversible choice.",
                 "cliffhanger": "The choice opens the next story question."},
            ],
            "production_note": f"Keep scenes consistent with: {brief['production_limit'] or 'a compact cast and limited locations'}.",
            "demo_note": "Sample content for workflow testing; replace with a live model for creative evaluation.",
        }


class OpenRouterGenerator:
    name = "openrouter"
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("OPENROUTER_MODEL", "")

    def _complete_json(self, prompt):
        if not self.api_key or not self.model:
            raise GenerationError("Set OPENROUTER_API_KEY and OPENROUTER_MODEL to use live generation.")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You develop original vertical short drama. Return only valid JSON. Do not reuse existing IP."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 1400,
        }
        req = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=45) as response:
                data = json.load(response)
        except HTTPError as exc:
            raise GenerationError(f"OpenRouter returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            raise GenerationError("OpenRouter could not be reached.") from exc
        except (ValueError, TypeError) as exc:
            raise GenerationError("OpenRouter returned invalid JSON.") from exc
        try:
            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(content)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise GenerationError("OpenRouter returned an unexpected response format.") from exc

    def generate_concepts(self, brief, revision_note=""):
        prompt = (
            "Create exactly three DISTINCT concepts for this original short drama. "
            "Return JSON: {\"concepts\":[{\"title\":str,\"logline\":str,\"hook\":str,"
            "\"core_conflict\":str,\"audience_fit\":str}]}. "
            f"Brief: {json.dumps(brief, ensure_ascii=False)}. Revision instruction: {revision_note or 'none'}."
        )
        data = self._complete_json(prompt)
        concepts = data.get("concepts") if isinstance(data, dict) else None
        required = ("title", "logline", "hook", "core_conflict", "audience_fit")
        if not isinstance(concepts, list) or len(concepts) != 3:
            raise GenerationError("The model did not return exactly three concepts.")
        output = []
        for i, item in enumerate(concepts, 1):
            if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip() for k in required):
                raise GenerationError("The model returned an incomplete concept.")
            output.append({"id": f"c{i}", **{k: item[k].strip() for k in required}})
        return output

    def generate_outline(self, brief, concept):
        prompt = (
            "Develop a three-episode outline for this ORIGINAL short drama concept. "
            "Return JSON: {\"series_title\":str,\"characters\":[{\"name\":str,\"goal\":str}],"
            "\"episodes\":[{\"number\":1,\"opening\":str,\"turn\":str,\"cliffhanger\":str}],"
            "\"production_note\":str}. Provide exactly three numbered episodes. "
            f"Brief: {json.dumps(brief, ensure_ascii=False)}. Concept: {json.dumps(concept, ensure_ascii=False)}."
        )
        data = self._complete_json(prompt)
        if not isinstance(data, dict) or not isinstance(data.get("episodes"), list) or len(data["episodes"]) != 3:
            raise GenerationError("The model did not return a three-episode outline.")
        for i, episode in enumerate(data["episodes"], 1):
            if not isinstance(episode, dict) or any(not isinstance(episode.get(k), str) or not episode[k].strip()
                                                     for k in ("opening", "turn", "cliffhanger")):
                raise GenerationError("The model returned an incomplete episode outline.")
            episode["number"] = i
        if not isinstance(data.get("characters"), list) or not data["characters"]:
            raise GenerationError("The model did not return characters.")
        return data
