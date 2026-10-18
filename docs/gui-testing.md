# GUI coverage and native tests

GUI coverage is tracked separately from the core package gate. The existing
`pyproject.toml` coverage settings still exclude `gui.py` and require 85% for the
core. SonarQube keeps its existing GUI coverage exclusion and core `coverage.xml`
input. The dedicated **GUI coverage baseline** CI job uses `.coveragerc-gui` to
include `gui.py`, measure branches, and require 80% combined statement/branch
coverage. It does not replace or lower the core gate.

Before native event-loop checks were added, the 23 existing GUI tests measured
about 37% coverage with branches enabled. Those tests mostly exercise helpers and
selected methods without constructing a Tk application. The first native
measurement on 2026-10-18, before subsequent GUI additions, reached about 91%.
The 80% baseline allows room for native integration paths that are intentionally not automated; new
behavior should still have focused assertions. Review the missing-line report
when changing the GUI, rather than adding tests only to reach a percentage.

## Run the native checks

Use Python 3.13 for parity with the coverage job. On Debian/Ubuntu, install
`python3-tk`, `xvfb` and `xauth`, then activate the development virtual environment:

```bash
python -m pip install -e '.[dev,vectorize,gui]' \
  'resvg-py>=0.5,<0.6'
SVGCONVERTER_NATIVE_GUI=1 xvfb-run -a pytest \
  --cov=svgconverter --cov-config=.coveragerc-gui \
  --cov-report=term-missing --cov-report=xml --cov-report=html
```

On an existing desktop display, omit `xvfb-run -a`. The explicit environment flag
opts into native tests; ordinary headless pytest runs skip them and keep running
the GUI unit tests. The separate job runs the full suite so native preview/drop
tests are included as the interface grows. VTracer, the preview renderer and
Tk drag-and-drop dependencies are installed for that job; normal core tests keep
their existing dependency policy.

The console report lists missing lines and branch arcs. `coverage-gui.xml` and
`htmlcov-gui/` are uploaded as the `gui-coverage` artifact for 14 days, including
when the coverage gate fails. Local GUI measurement uses `.coverage-gui`, leaving
the core data and XML report independent. Open `htmlcov-gui/index.html` to inspect
executed and missing paths.

## Behavior covered by the native baseline

`tests/test_gui_native.py` constructs the real application and dispatches actual
Tk button commands and queued worker events. It checks:

- Embed and Vectorize conversions, selected preprocessing options, output metrics,
  completion controls, reset, and a second conversion after the first poll loop.
- Mixed converted/skipped/failed batches without replacing a skipped output.
- Cancellation at a synchronized file boundary, including progress, cancellation
  feedback and stopping the worker/event polling lifecycle.
- Expected and unexpected worker failures restoring editable controls and useful
  error feedback, plus invalid options that never start a worker.
- Language switching while work is pending and after completion without losing
  selection, worker state or conversion results.

Workers use real conversion APIs, with explicit synchronization only where a
cancellation or pending state must be observed. The tests wait for state changes
with bounded deadlines instead of assuming a fixed conversion duration. Modal
error dialogs are intercepted so the suite cannot wait for a person to close
one. Assertions concern behavior and data; no pixel positions or screenshot
comparisons are part of this gate.

## Remaining integration gaps

The coverage job runs on Ubuntu 24.04 with Python 3.13, Tcl/Tk 8.6 and Xvfb. It
covers event-loop behavior on that environment, not every OS desktop integration.
Windows/macOS native file dialogs, OS file-manager launching, window-manager
focus/scaling, display accessibility, and real external drag gestures still need
manual platform checks. OS-specific packaged startup/conversion checks remain
separate from this coverage job.

The optional drag-and-drop extension may not load with a different Tcl/Tk major
version, including some local Tcl/Tk 9 installations. Its supported-environment
check and fallback should be assessed separately; a local run without that backend
cannot establish the same integration coverage as the CI runtime. Preview
rendering/backend failures, cancellation/closing behavior, and optional backend
availability are covered by their focused tests as those features are included.
