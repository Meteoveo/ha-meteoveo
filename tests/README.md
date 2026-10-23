# Tests

```bash
.venv/bin/python -m pytest -q
```

The suite runs on `pytest-homeassistant-custom-component`: config flows,
options, re-authentication and entities are exercised through a real Home
Assistant instance, with the MeteoVeo service mocked. Pure logic -- unit
conversion, plausibility limits, credential handling, request shapes -- is
tested directly.
