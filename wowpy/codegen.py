"""Generate a wowpy program from a Blockly workspace (user story US-003).

The editor also generates code live in the browser; this module is the
authoritative version used when saving and running, so ``programs/<name>.py``
always matches ``programs/<name>.json``.

Input is Blockly's JSON serialisation (``Blockly.serialization.workspaces.save``)
plus the custom block definitions from ``blocks/``. Output is a module defining
``async def main(mip)`` and/or event handlers registered on ``program``.
"""

import re

from .blocks import BLOCKS_BY_TYPE

HEADER = '''"""Generated from {source} by wowpy - do not edit by hand."""

import asyncio
'''

INDENT = "    "


def _indent(text, level=1):
    pad = INDENT * level
    return "\n".join(pad + line if line.strip() else line for line in text.split("\n"))


def slug(name):
    """Turn a block or program name into a safe identifier/filename stem."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(name)).strip("-").lower()
    return s or "unnamed"


def func_name(name):
    return slug(name).replace("-", "_")


class Generator:
    def __init__(self, custom_blocks=None):
        # name -> {"name", "params": [...], "workspace": {...}}
        self.custom = {c["name"]: c for c in (custom_blocks or [])}
        self._emitted = []          # generated custom-block functions
        self._emitting = set()      # cycle guard
        self._idents = {}           # block id -> unique identifier fragment

    # -- values ------------------------------------------------------------

    def value(self, block):
        """Generate a Python expression for a value (reporter) block."""
        if block is None:
            return "None"
        t = block.get("type")
        fields = block.get("fields", {})
        inputs = block.get("inputs", {})

        # Standard Blockly value blocks
        if t == "math_number":
            return repr(fields.get("NUM", 0))
        if t == "text":
            return repr(fields.get("TEXT", ""))
        if t == "logic_boolean":
            return "True" if fields.get("BOOL") == "TRUE" else "False"
        if t == "logic_null":
            return "None"
        if t == "variables_get":
            return func_name(self._var_name(block))
        if t == "custom_param":
            # Reference to a parameter of the enclosing custom block.
            return func_name(fields.get("NAME", "param"))
        if t == "logic_compare":
            op = {"EQ": "==", "NEQ": "!=", "LT": "<", "LTE": "<=", "GT": ">", "GTE": ">="}[fields.get("OP", "EQ")]
            return f"({self._input_value(inputs, 'A')} {op} {self._input_value(inputs, 'B')})"
        if t == "logic_operation":
            op = "and" if fields.get("OP", "AND") == "AND" else "or"
            return f"({self._input_value(inputs, 'A')} {op} {self._input_value(inputs, 'B')})"
        if t == "logic_negate":
            return f"(not {self._input_value(inputs, 'BOOL')})"
        if t == "math_arithmetic":
            op = {"ADD": "+", "MINUS": "-", "MULTIPLY": "*", "DIVIDE": "/", "POWER": "**"}[fields.get("OP", "ADD")]
            return f"({self._input_value(inputs, 'A')} {op} {self._input_value(inputs, 'B')})"
        if t == "math_random_int":
            return f"random.randint({self._input_value(inputs, 'FROM')}, {self._input_value(inputs, 'TO')})"
        if t == "text_join":
            parts = [self._input_value(inputs, k) for k in sorted(inputs)]
            return "''.join(str(x) for x in (" + ", ".join(parts) + ",))" if parts else "''"

        spec = BLOCKS_BY_TYPE.get(t)
        if spec and spec.get("shape") == "value":
            return self._render(spec["code"], block)
        return "None"

    def _var_name(self, block):
        f = block.get("fields", {}).get("VAR")
        if isinstance(f, dict):
            return f.get("name") or f.get("id") or "var"
        return f or "var"

    def _input_value(self, inputs, name):
        entry = inputs.get(name) or {}
        return self.value(entry.get("block") or entry.get("shadow"))

    # -- statements --------------------------------------------------------

    def statements(self, block):
        """Generate a statement stack starting at ``block`` (following ``next``)."""
        lines = []
        while block:
            lines.append(self.statement(block))
            nxt = block.get("next") or {}
            block = nxt.get("block")
        body = "\n".join(l for l in lines if l)
        return body or "pass"

    def statement(self, block):
        t = block.get("type")
        fields = block.get("fields", {})
        inputs = block.get("inputs", {})
        bid = block.get("id", "")

        if t == "controls_if":
            out = []
            i = 0
            while f"IF{i}" in inputs:
                kw = "if" if i == 0 else "elif"
                cond = self._input_value(inputs, f"IF{i}")
                body = self._input_statements(inputs, f"DO{i}")
                out.append(f"{kw} {cond}:\n{_indent(body)}")
                i += 1
            if "ELSE" in inputs:
                out.append("else:\n" + _indent(self._input_statements(inputs, "ELSE")))
            return "\n".join(out)
        if t == "controls_repeat_ext":
            n = self._input_value(inputs, "TIMES")
            body = self._input_statements(inputs, "DO")
            return f"for _ in range(int({n})):\n{_indent(body)}\n{INDENT}await asyncio.sleep(0)"
        if t == "controls_whileUntil":
            cond = self._input_value(inputs, "BOOL")
            if fields.get("MODE") == "UNTIL":
                cond = f"not {cond}"
            body = self._input_statements(inputs, "DO")
            return f"while {cond}:\n{_indent(body)}\n{INDENT}await asyncio.sleep(0)"
        if t == "controls_flow_statements":
            return "break" if fields.get("FLOW") == "BREAK" else "continue"
        if t == "variables_set":
            return f"{func_name(self._var_name(block))} = {self._input_value(inputs, 'VALUE')}"
        if t == "math_change":
            name = func_name(self._var_name(block))
            return f"{name} = {name} + {self._input_value(inputs, 'DELTA')}"

        if t in self.custom or t.startswith("custom_"):
            return self._custom_call(block)

        spec = BLOCKS_BY_TYPE.get(t)
        if spec is None:
            return ""
        return self._render(spec["code"], block)

    def _input_statements(self, inputs, name):
        entry = inputs.get(name) or {}
        return self.statements(entry.get("block"))

    # -- templates ---------------------------------------------------------

    def _render(self, template, block):
        fields = block.get("fields", {})
        inputs = block.get("inputs", {})
        bid = block.get("id", "")
        out = template

        # {^NAME} -> indented statement stack
        for name in re.findall(r"\{\^(\w+)\}", out):
            body = self._input_statements(inputs, name)
            out = out.replace("{^" + name + "}", _indent(body))
        # {$NAME} -> value expression
        for name in re.findall(r"\{\$(\w+)\}", out):
            out = out.replace("{$" + name + "}", self._input_value(inputs, name))
        # {id!name} -> id usable inside an identifier; {id} -> id as a literal
        out = out.replace("{id!name}", self._ident(bid))
        out = out.replace("{id}", repr(bid))
        # {FIELD}, {FIELD!r} (quoted) and {FIELD!rgb} ("#rrggbb" -> "r, g, b").
        # A field promoted to a custom-block parameter is an input, not a field.
        for name, bang in re.findall(r"\{(\w+)(!r(?:gb)?)?\}", out):
            if name not in fields:
                if name in inputs:
                    out = out.replace("{" + name + (bang or "") + "}", self._input_value(inputs, name))
                continue
            value = fields[name]
            if bang == "!rgb":
                c = str(value).lstrip("#")
                text = f"{int(c[0:2], 16)}, {int(c[2:4], 16)}, {int(c[4:6], 16)}"
            elif bang:
                text = repr(value)
            else:
                text = str(value)
            out = out.replace("{" + name + (bang or "") + "}", text)
        return out

    def _ident(self, bid):
        """A unique identifier fragment for ``bid``.

        Blockly ids contain characters that are not valid in a Python name, and
        stripping them can make two different ids collide - which would silently
        merge two event handlers into one function.
        """
        if bid not in self._idents:
            base = re.sub(r"\W", "_", str(bid)) or "block"
            candidate, n = base, 1
            while candidate in self._idents.values():
                n += 1
                candidate = f"{base}_{n}"
            self._idents[bid] = candidate
        return self._idents[bid]

    # -- custom blocks -----------------------------------------------------

    def _custom_call(self, block):
        name = block.get("type")
        definition = self.custom.get(name)
        if definition is None:
            return ""
        self.emit_custom(name)
        args = ["mip"] + [self._input_value(block.get("inputs", {}), p["name"].upper())
                          for p in definition.get("params", [])]
        return f"await _step({block.get('id', '')!r})\nawait {func_name(name)}({', '.join(args)})"

    def emit_custom(self, name):
        """Generate the function for custom block ``name`` once."""
        definition = self.custom.get(name)
        if definition is None or name in self._emitting:
            return
        if any(f"async def {func_name(name)}(" in e for e in self._emitted):
            return
        self._emitting.add(name)
        params = ["mip"] + [func_name(p["name"]) for p in definition.get("params", [])]
        body = self.statements(self._first_block(definition.get("workspace", {})))
        self._emitted.append(f"async def {func_name(name)}({', '.join(params)}):\n{_indent(body)}")
        self._emitting.discard(name)

    @staticmethod
    def _first_block(workspace):
        blocks = (workspace.get("blocks") or {}).get("blocks") or []
        return blocks[0] if blocks else None

    # -- whole workspace ---------------------------------------------------

    def generate(self, workspace, source="the block editor"):
        top = (workspace.get("blocks") or {}).get("blocks") or []
        main_parts, event_parts = [], []
        for block in top:
            t = block.get("type")
            spec = BLOCKS_BY_TYPE.get(t)
            if spec is None or spec.get("shape") != "hat":
                continue
            code = self._render(spec["code"], block)
            (main_parts if t == "mip_on_start" else event_parts).append(code)

        chunks = [HEADER.format(source=source)]
        chunks.extend(self._emitted)
        chunks.extend(main_parts)
        chunks.extend(event_parts)
        if len(chunks) == 1:
            chunks.append("async def main(mip):\n    pass")
        return "\n\n".join(c.rstrip() for c in chunks) + "\n"


def generate(workspace, custom_blocks=None, source="the block editor"):
    gen = Generator(custom_blocks)
    # Custom blocks used anywhere must be emitted before the code that calls them.
    body = gen.generate(workspace, source)
    if gen._emitted:
        # Re-render so the emitted functions appear above their callers.
        gen2 = Generator(custom_blocks)
        for name in list(gen.custom):
            if f"{func_name(name)}(" in body:
                gen2.emit_custom(name)
        body = gen2.generate(workspace, source)
    return body
