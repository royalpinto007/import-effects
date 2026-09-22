# Contributing

Contributions are welcome. Please open an issue before changing public behavior or adding a new effect kind.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
ruff format .
ruff check .
mypy
pytest --cov
python -m build
twine check dist/*
```

Tests should exercise behavior through the public API or CLI in a real child interpreter. Do not add observations that cannot be reproduced reliably, and keep confidence and attribution claims conservative.

Use Conventional Commits and do not commit captured environment data, tokens, local package sources, or generated artifacts.

