from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class TemplateRegistry:
    def __init__(self, templates_dir: Path) -> None:
        self.templates_dir = templates_dir
        self._templates = self._load_templates()

    def _load_templates(self) -> dict[str, dict[str, Any]]:
        templates: dict[str, dict[str, Any]] = {}
        for path in sorted(self.templates_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text())
            templates[data["id"]] = data
        return templates

    def get(self, template_id: str) -> dict[str, Any]:
        template = self._templates.get(template_id)
        if template is None:
            raise KeyError(f"Unknown template_id: {template_id}")
        return template

    def list_templates(self) -> list[dict[str, Any]]:
        return list(self._templates.values())

    def ids(self) -> list[str]:
        return sorted(self._templates)

    def editable_sections_by_template(self) -> dict[str, list[str]]:
        return {
            template_id: list(template.get("editable_sections", []))
            for template_id, template in sorted(self._templates.items())
        }
