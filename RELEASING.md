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
   builds and smoke-tests a self-contained Windows GUI executable, and then
   creates the GitHub Release with all generated artifacts.

The release assets include a versioned `SVGConverter-vX.Y.Z-windows-x86_64.exe`
that does not require a local Python installation. The workflow explicitly
bundles GUI language resources and the VTracer Python/native backend. Both the
build and release workflows run Embed and Vectorize conversions through the
packaged executable with Python removed from `PATH`, and validate embedded
images, generated paths, Unicode paths, and failure exit codes before uploading
the asset. These checks use its `--cli` prefix; normal launch still opens the GUI.
The bundled native backend increases executable size relative to the 18.5 MB
v1.8.1 artifact; inspect the generated artifact size when reviewing a release.
Before tagging a desktop release, download the
Windows CI artifact and manually verify file/folder selection, progress,
cancellation, and language switching on a clean Windows machine.

Windows builds install `.[vectorize,gui]` and collect all `tkinterdnd2` data and
native libraries alongside VTracer. Both Windows workflows run
`SVGCONVERTER_NATIVE_GUI=1 python -m pytest -q tests/test_dragdrop_native.py`
before packaging. This requires a display and a compatible Tcl/Tk/tkdnd runtime;
the test must load the native extension rather than accept the picker fallback.
It delivers Tcl file-drop events through the registered target, covering mixed
files/folders, spaces, Unicode, deduplication, invalid items, and busy-state
refusal without starting conversion. The packaged conversion/startup checks
remain separate. Before tagging, also test actual Explorer drag gestures against
the downloaded executable, including partial invalid drops and conversion in
progress.

The optional `gui` extra does not install Tkinter or Tcl/Tk. It restricts
`tkinterdnd2` to the 0.4.3 series for Tcl/Tk 8.x compatibility; 0.4.4.1 includes a
macOS arm64 Tcl 9 binary that cannot load in the Python 3.13/Tk 8.6 runner.
All native jobs must pass before upgrading this dependency. Incompatible Tk 9
builds or unavailable OS/CPU binaries fall back to ordinary file/folder pickers.
Linux/macOS Python users retain those controls even without native drop support.

Linux/macOS standalone assets are currently a no-go for public releases. The
separate [native evaluation workflow](.github/workflows/native-distributions.yml)
retains temporary artifacts for seven days and is not a publishing job. See the
[distribution decision and promotion criteria](docs/native-distributions.md) before
considering new release assets.
