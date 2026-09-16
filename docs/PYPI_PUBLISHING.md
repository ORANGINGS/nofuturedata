# PyPI publishing

NoFutureData uses PyPI Trusted Publishing so the repository does not need a
long-lived API token.

The GitHub workflow is intentionally `workflow_dispatch` only. It will not
publish automatically when a release is created. Its `publish` input defaults
to `false`, so maintainers can verify the build job without touching PyPI.

## One-time PyPI setup

Create the `nofuturedata` project or a pending publisher on PyPI and configure
this GitHub publisher identity:

- owner: `ORANGINGS`
- repository: `nofuturedata`
- workflow: `publish.yml`
- environment: `pypi`

Then create a GitHub environment named `pypi`. Environment protection rules are
optional but recommended for manual release control.

## Publish

1. Verify the version in `pyproject.toml` and `src/nofuturedata/__init__.py`.
2. Verify CI is green and the matching Git tag/release exists.
3. In GitHub Actions, run **publish-python-package** manually with `publish`
   checked.
4. Confirm the package page and install the uploaded wheel in a clean environment.

The workflow builds both wheel and source distribution with `build==1.6.1`,
passes them between jobs as a GitHub artifact, then authenticates to PyPI using
OIDC through `pypa/gh-action-pypi-publish`.
