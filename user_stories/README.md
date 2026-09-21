# User stories

One folder per story, numbered `US-NNN-short-slug/`:

- `story.md` — the story itself (As a / I want / So that), the decisions taken
  while refining it, and what is explicitly out of scope.
- `*.feature` — Gherkin acceptance criteria. Every scenario must be checkable,
  either by an automated test (preferably against the mock robot) or by a
  manual step on the real MiP; scenarios that need hardware are tagged
  `@hardware`.

A story is done when every scenario in its `.feature` files passes.
