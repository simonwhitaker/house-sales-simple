# Agent Instructions

## Validation Gate

After making any changes to Python code in this repository, run Ruff before handing the work back:

```sh
uv run ruff format --check .
uv run ruff check .
```

The lint command includes import sorting via Ruff's `I` rules. If Ruff reports
formatting, lint, or import-order issues, fix them and rerun the commands until
they pass.
