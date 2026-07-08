# Release Checklist

Steps for cutting a Chronicle release, including the one-time manual setup
required before `.github/workflows/pypi.yml` can publish `chronicle-sdk`
automatically.

## One-time: first PyPI upload

`.github/workflows/pypi.yml` publishes on every GitHub Release, but PyPI
requires the package to exist on PyPI *before* a CI token can push to it (you
can't create a brand-new project name via an API token alone in the normal
flow). The very first `chronicle-sdk` release has to be uploaded by hand:

1. Create a PyPI account at https://pypi.org/account/register/ if you don't
   have one, and enable 2FA (PyPI requires it for new projects).
2. Build the distribution locally:
   ```bash
   cd sdk
   pip install build twine
   rm -rf dist build *.egg-info
   python -m build
   twine check dist/*
   ```
3. Upload it manually, authenticating with your PyPI account (an API token
   scoped to your account, not a project — create one at
   https://pypi.org/manage/account/token/):
   ```bash
   twine upload dist/*
   ```
4. Once `chronicle-sdk` exists on PyPI, create a **project-scoped** API token
   (https://pypi.org/manage/project/chronicle-sdk/settings/) — narrower than
   the account-wide token used for the first upload.
5. Add that token as a repository secret named `PYPI_API_TOKEN`
   (Settings → Secrets and variables → Actions → New repository secret).
6. Add a GitHub Environment named `pypi` (Settings → Environments → New
   environment) — `pypi.yml` deploys to this environment, which lets you
   optionally require manual approval before a publish runs.

After this one-time setup, every subsequent release publishes automatically:
`pypi.yml` triggers on `release: published`, builds sdist+wheel, runs
`twine check`, and uploads using the `PYPI_API_TOKEN` secret.

## Every release

1. **Version bump**: update the version in every location that carries one:
   - `sdk/pyproject.toml` (`project.version`)
   - `sdk/src/chronicle/__init__.py` (`__version__`)
   - `server/pyproject.toml` (`project.version`)
   - `server/src/__init__.py` (`__version__`)
   - `app/package.json` (`version`)
   - `app/src-tauri/tauri.conf.json` (`version`)
   - `app/src-tauri/Cargo.toml` (`version`)
2. **CHANGELOG.md**: add a dated entry for the new version summarizing
   what changed.
3. **Full verification** — run everything green before tagging:
   ```bash
   cd server && ruff check src tests && mypy src && pytest
   cd ../sdk && ruff check src tests && mypy src && pytest
   cd ../app && npx eslint . && npx tsc --noEmit && npx vitest run
   ```
4. **Build and check the SDK distribution** (catches metadata regressions
   before they reach PyPI):
   ```bash
   cd sdk && rm -rf dist build *.egg-info && python -m build && twine check dist/*
   ```
5. **Tag and push**:
   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```
6. **Create the GitHub Release** from the tag, pasting the CHANGELOG.md
   entry as the release body. Publishing the release triggers:
   - `pypi.yml` → builds and uploads `chronicle-sdk` to PyPI.
   - `release.yml` → builds the desktop app installers (see that workflow
     for the Tauri sidecar/auto-updater signing requirements).
7. **Verify the publish**: `pip install chronicle-agent-sdk==X.Y.Z` in a clean
   virtualenv and confirm `chronicle --help` works and `chronicle.__version__`
   matches.
8. **Smoke-test the desktop app installer** on at least one platform before
   announcing the release.

## Rolling back a bad PyPI release

PyPI never allows re-uploading the same version number, even after deleting
a release. If a published version is broken:
1. Yank it (does not delete it, but pip won't select it by default):
   `https://pypi.org/manage/project/chronicle-sdk/release/X.Y.Z/` → "Yank".
2. Fix the issue, bump to the next patch version, and release again through
   the normal flow above.
