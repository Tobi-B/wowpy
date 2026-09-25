"""Reading and writing programs and custom blocks (user story US-003).

Programs live in ``programs/<slug>.json`` (Blockly workspace) plus a generated
``programs/<slug>.py``; custom blocks in ``blocks/<slug>.json``. Both are plain
files in the project so they can be versioned with Git and run without a
browser.
"""

import json
import re
from pathlib import Path

from . import blockcode, codegen

NAME_RE = re.compile(r"^[A-Za-z0-9 \-]+$")
NAME_HINT = "letters, digits, spaces and dashes only"
STEP_CALL = re.compile(r"^\s*await _step\(.*\)\s*$")

# Fields save_block() owns; everything else in a stored block is carried over.
MANAGED_KEYS = {"name", "colour", "params", "workspace", "mode", "code"}


class NameError_(ValueError):
    """Rejected program/block name."""


class NameTaken(ValueError):
    """A new block would overwrite an existing one."""


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

    def save_block(self, definition, create=False):
        """Store a custom block.

        ``{name, colour, params}`` plus either a ``workspace`` (mode
        ``blocks``) or hand-written ``code`` (mode ``python``). Python bodies
        are validated first, so a block that cannot run is never written.
        """
        name = check_name(definition.get("name", ""))
        path, _ = self._paths(self.blocks, name)
        if create and path.exists():
            raise NameTaken(f"es gibt schon einen Baustein namens {name!r}")
        params = definition.get("params", [])
        data = {"name": name, "colour": definition.get("colour", 330), "params": params}

        if definition.get("mode") == "python":
            data["mode"] = "python"
            data["code"] = blockcode.validate(definition.get("code"), params)
            # Kept so a converted block can be regenerated from where it came
            # from; a block written from scratch simply has none.
            workspace = definition.get("workspace")
            if not workspace and path.exists():
                workspace = self.load_block(name).get("workspace")
            if workspace:
                data["workspace"] = workspace
        else:
            data["workspace"] = definition.get("workspace", {})

        # Keep any metadata this class does not manage (e.g. "shipped"), from
        # the definition passed in and from what is already on disk, so a round
        # trip through save does not quietly drop it.
        sources = [definition]
        if path.exists():
            sources.append(self.load_block(name))
        for source in sources:
            for key, value in source.items():
                if key not in MANAGED_KEYS and key not in data:
                    data[key] = value

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return data

    def block_body(self, name):
        """The Python body this block generates today - the seed for a conversion."""
        definition = self.load_block(name)
        if definition.get("mode") == "python":
            return codegen.normalise_code(definition.get("code"))
        gen = codegen.Generator([definition])
        gen.emit_custom(definition["name"])
        if not gen._emitted:
            return "pass"
        # drop the "async def ...:" line and one level of indentation
        lines = gen._emitted[0].split("\n")[1:]
        lines = [line[4:] if line.startswith("    ") else line for line in lines]
        # _step() marks the running block for highlighting. A converted block
        # has no inner blocks to highlight, and the calls would only be noise
        # in code a person edits by hand.
        lines = [line for line in lines if not STEP_CALL.match(line)]
        return "\n".join(lines) or "pass"

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
