"""Reading and writing programs and custom blocks (user story US-003).

Programs live in ``programs/<slug>.json`` (Blockly workspace) plus a generated
``programs/<slug>.py``; custom blocks in ``blocks/<slug>.json``. Both are plain
files in the project so they can be versioned with Git and run without a
browser.
"""

import json
import re
from pathlib import Path

from . import codegen

NAME_RE = re.compile(r"^[A-Za-z0-9 \-]+$")
NAME_HINT = "letters, digits, spaces and dashes only"


class NameError_(ValueError):
    """Rejected program/block name."""


def check_name(name):
    """Return ``name`` if it is safe to turn into a filename, else raise."""
    name = str(name).strip()
    if not name or not NAME_RE.match(name):
        raise NameError_(NAME_HINT)
    return name


class Store:
    def __init__(self, root="."):
        self.root = Path(root)
        self.programs = self.root / "programs"
        self.blocks = self.root / "blocks"

    def _paths(self, folder, name):
        stem = codegen.slug(check_name(name))
        # slug() strips everything outside [a-z0-9-], so the stem cannot escape
        # the folder; guard anyway in case that ever changes.
        path = (folder / f"{stem}.json").resolve()
        if folder.resolve() not in path.parents:
            raise NameError_(NAME_HINT)
        return path, (folder / f"{stem}.py")

    # -- custom blocks -----------------------------------------------------

    def list_blocks(self):
        out = []
        if self.blocks.is_dir():
            for path in sorted(self.blocks.glob("*.json")):
                try:
                    out.append(json.loads(path.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    continue
        return out

    def load_block(self, name):
        path, _ = self._paths(self.blocks, name)
        if not path.exists():
            raise FileNotFoundError(name)
        return json.loads(path.read_text(encoding="utf-8"))

    def save_block(self, definition):
        """Store a custom block ``{name, colour, params, workspace}``."""
        name = check_name(definition.get("name", ""))
        path, _ = self._paths(self.blocks, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"name": name, "colour": definition.get("colour", 330),
                "params": definition.get("params", []), "workspace": definition.get("workspace", {})}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return data

    def delete_block(self, name):
        path, _ = self._paths(self.blocks, name)
        if path.exists():
            path.unlink()

    def block_usage(self, name):
        """How many saved programs still use custom block ``name``."""
        count = 0
        if self.programs.is_dir():
            for path in self.programs.glob("*.json"):
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                count += text.count(f'"type": "{name}"')
        return count

    # -- programs ----------------------------------------------------------

    def list_programs(self):
        if not self.programs.is_dir():
            return []
        names = []
        for path in sorted(self.programs.glob("*.json")):
            try:
                names.append(json.loads(path.read_text(encoding="utf-8")).get("name", path.stem))
            except (json.JSONDecodeError, OSError):
                names.append(path.stem)
        return names

    def load_program(self, name):
        path, _ = self._paths(self.programs, name)
        if not path.exists():
            raise FileNotFoundError(name)
        return json.loads(path.read_text(encoding="utf-8"))

    def save_program(self, name, workspace):
        """Write the workspace and its generated Python; returns the code."""
        name = check_name(name)
        json_path, py_path = self._paths(self.programs, name)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        code = codegen.generate(workspace, self.list_blocks(), source=f"programs/{json_path.name}")
        json_path.write_text(json.dumps({"name": name, "workspace": workspace}, indent=2) + "\n", encoding="utf-8")
        py_path.write_text(code, encoding="utf-8")
        return code
