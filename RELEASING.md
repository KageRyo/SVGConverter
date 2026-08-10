# Releasing SVGConverter

This is a maintainer guide, not an end-user installation guide.

## One-time PyPI setup

Configure a PyPI Trusted Publisher before the first release:

- owner: `KageRyo`
- repository: `SVGConverter`
- workflow: `release.yml`
- environment: `pypi`

The workflow uses GitHub Actions OIDC, so it does not require a long-lived
PyPI API token.

## Release checklist

1. Complete work through GitHub Flow and squash merge it into `main`.
2. Update the package version in `pyproject.toml` and
   `src/svgconverter/__init__.py`, then move the relevant entries in
   `CHANGELOG.md` into a dated release section.
3. Confirm all CI checks are green and that `python -m build` plus
   `python -m twine check dist/*` pass locally.
4. On the merged commit, create and push an annotated tag matching the package
   version:

   ```bash
   git checkout main
   git pull --ff-only origin main
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

5. Monitor the `Release to PyPI` workflow. It checks the tag/version match,
   builds and validates distributions, publishes through Trusted Publishing,
   and then creates the GitHub Release with the generated artifacts.
