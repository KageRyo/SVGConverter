# Linux and macOS desktop distribution evaluation

The decision for this release cycle is **no-go for public Linux/macOS standalone
release assets**. Keep the Python package as the supported installation route on
these systems. Continue the existing Windows x86_64 executable distribution.

The native evaluation workflow makes future packaging decisions repeatable. It
builds temporary CI artifacts for the following targets, but does not add assets
to GitHub Releases or make a compatibility/support promise for those archives:

| Evaluation target | Runner / CPU | Candidate format | Public standalone support |
| --- | --- | --- | --- |
| Ubuntu 24.04 | `ubuntu-24.04`, x86_64 | PyInstaller directory in `.tar.gz` | No |
| macOS 15 | `macos-15`, Apple Silicon arm64 | PyInstaller `.app` in `.tar.gz` | No |
| Other Linux distributions/CPUs, Intel Macs, older macOS | Not evaluated | Python installation | No |

These explicit runner labels avoid changes hidden behind `*-latest`. GitHub's
[runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
currently identifies the selected Linux label as x64 and the selected macOS label
as arm64. The macOS artifact is a native arm64 build, not universal2; no Rosetta
or Intel compatibility is implied.

## What the evaluation proves

[Evaluate native desktop distributions](../.github/workflows/native-distributions.yml)
runs on relevant source/packaging pull requests and merged changes, and can also
be started manually. Each target uses Python 3.13 and a fresh virtual environment
with Pillow, VTracer, tkinterdnd2 and PyInstaller. Logs record installed dependency versions,
the executable architecture and bundle size.

Before packaging, the workflow runs real Embed and Vectorize conversions through
the source launcher, initializes the actual Tk application on a display, and runs
its event loop long enough to verify a viewable window. Linux uses Xvfb; macOS
uses the runner's desktop session. A separate native drag-and-drop smoke check
loads tkdnd, registers the GUI target, and delivers Tcl file-drop events for mixed
files/folders, Unicode and space-containing paths, duplicates, invalid items and
busy-state refusal. It confirms drops only update selection. This check exercises
the source application's native bindings rather than an OS file-manager gesture.
It then builds the candidate bundle, including tkinterdnd2's native data, and runs
conversions through that exact frozen executable with Python removed from `PATH`,
Python and dynamic-library path overrides removed, and a temporary working directory outside
the checkout. The smoke check verifies:

- A logo whose filename contains spaces and Unicode converts in both modes.
- Embed output contains an SVG image, and Vectorize output contains path geometry
  without embedded images, with the expected SVG namespace.
- A malformed image returns exit code 1 without leaving an output file.
- The frozen application's default GUI launch stays running for three seconds.

The frozen GUI startup check catches immediate import/Tk/resource failures; it
does not exercise file pickers, window-manager behavior, cancellation or desktop
integration. Source window validation and frozen startup are separate checks.
Passing on a build runner also does not establish clean-machine portability.

Only successful builds are archived. The seven-day CI artifacts preserve bundle
symlinks and executable permissions inside `.tar.gz`; they are evaluation inputs,
not release downloads. No signing secrets, publication permissions or new release
workflow dependencies are introduced.

An initial local Linux x86_64 probe on WSL (Python 3.12, Tcl/Tk 9) passed
source conversions and window initialization. Its first frozen build converted
images but failed GUI import because Tcl shared libraries were missing; the new
smoke check rejected that build. After exposing the interpreter's native library
directory to PyInstaller during packaging, the frozen conversions and GUI startup
passed with library-path overrides removed at runtime. This host is not either
selected CI runner, and this result establishes neither Ubuntu 24.04 portability
nor macOS support; those native job results must be checked independently.

## Why public standalone distribution remains deferred

Two additional native builds per relevant change are a manageable evaluation
baseline. Public distribution would add recurring work that these jobs do not
cover: a supported Linux distribution/ABI matrix, clean desktop installation
checks, macOS signing credentials and notarization, release artifact verification,
and separate CPU builds with compatible Pillow/VTracer/Tk binaries. There is no
maintained clean-machine matrix or signing/notarization pipeline in this project.
Adding public assets now would commit to support beyond the available evidence.

A future go decision requires a named minimum OS/CPU matrix, independent clean-OS
launch/conversion checks, a maintainer for failures in each release, and a release
pipeline that publishes only validated artifacts. For macOS it must also include
Developer ID signing/notarization. Reassess using the workflow's timing, dependency
logs, artifact sizes and observed failures, rather than assuming a successful
build on one machine is enough. Additional AppImage, Flatpak, DMG and universal2
formats are outside this evaluation.

## Linux runtime limits

PyInstaller does not bundle glibc; its
[Linux compatibility guidance](https://pyinstaller.org/en/stable/usage.html#making-gnu-linux-apps-forward-compatible)
recommends building on the oldest intended distribution. This evaluation builds
on Ubuntu 24.04 and makes no claim for older glibc systems, musl/Alpine or other
Linux distributions. The directory bundle avoids one-file extraction requirements.

Tk needs a graphical display and system X11/font libraries. The workflow installs
`libx11-6`, `libxext6`, `libxrender1` and `libxft2`; Xvfb and `xauth` provide the CI
display. A normal desktop needs an available X11 display or compatible XWayland
session. The archive is not a static binary or a replacement for OS libraries;
missing-library reports on another system require a new compatibility test.

For Python installation on Debian/Ubuntu, install `python3-venv` and `python3-tk`
with the system package manager first. Other distributions provide Tk through
their Python/Tk packages. Check Tk before launching the application:

```bash
python3 -m tkinter
python3 -m venv .venv
. .venv/bin/activate
python -m pip install 'svgconverter[vectorize,gui]'
svgconverter-gui
```

Use `python -m pip install svgconverter` if only Embed is needed. CLI conversion
does not require a display; the GUI does.

The `gui` extra adds file/folder dropping and does not install Tcl/Tk itself. The
pinned tkdnd binaries target Tcl/Tk 8.x; incompatible Tk 9 or unavailable native
OS/CPU libraries leave ordinary picker controls usable. Native CI must load the
extension for its explicit drop smoke check instead of accepting that fallback.

## macOS runtime and trust limits

Use a Python installation with working Tk support, then use the same virtual
environment commands above. `python3 -m tkinter` verifies that the selected
interpreter can open a window. See Python's
[macOS installation guide](https://docs.python.org/3/using/mac.html) for interpreter
and Tcl/Tk installation guidance. The optional VTracer backend must support the
selected Python version and CPU; a native arm64 CI result does not validate an
Intel installation.

PyInstaller performs
[ad-hoc signing when no identity is supplied](https://pyinstaller.org/en/stable/usage.html#cmdoption-codesign-identity).
That is what these evaluation builds use. They have no Developer ID identity,
notarization ticket or stapling step. A locally launched runner artifact does not
prove Gatekeeper acceptance after a browser download. Apple's
[notarization guidance](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
describes the additional distribution requirements. Python installation remains
the supported route while the standalone release process is deferred.
