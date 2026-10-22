# Contributor setup

1. Read the package overview and inspect the small modules under `src/repo_guide/`.
2. Configuration defaults are in `src/repo_guide/config.py`; identity validation is in `src/repo_guide/auth.py`.
3. Report formatting is in `src/repo_guide/report.py` and should remain covered by focused tests.
4. No test framework or external service is required by this synthetic fixture.
5. A possible starter change is an optional report title format, but confirm the expected behavior with a maintainer before implementing it.
