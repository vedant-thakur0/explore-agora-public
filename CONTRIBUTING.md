# Contributing

Thanks for your interest in AGORA. This is a research toolkit, so contributions that improve correctness, documentation, or reproducibility are especially welcome.

## Getting set up

```bash
pip install -r requirements.txt
cp .env.example .env  # then fill in your keys
python3 -m pytest pipeline/tests
```

## Pull requests

- Open an issue first for non-trivial changes so we can align on scope.
- Keep changes focused: one logical change per PR.
- Add or update tests when touching pipeline behavior.
- Run `python3 -m pytest pipeline/tests` before submitting.

## Code style

- Python 3.9+ syntax.
- Match existing patterns — see [`CLAUDE.md`](CLAUDE.md) for repo conventions.
- Path constants belong in `pipeline/config.py`.

## Reporting issues

Include: what you ran, what you expected, what happened, and the relevant section of any traceback.
