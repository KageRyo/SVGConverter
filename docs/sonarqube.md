# SonarQube Cloud

SVGConverter uses CI-based SonarQube Cloud analysis in addition to Ruff,
Pyright, pytest, and pytest-cov. The repository keeps quality checks, build
checks, SonarQube analysis, and release work in separate workflows. The Sonar
workflow generates its own Cobertura report; it does not depend on an artifact
from another workflow.

## One-time repository setup

Import and bind the public `KageRyo/SVGConverter` repository in SonarQube
Cloud, then disable Automatic Analysis for the project. CI-based analysis is
required so that the generated `coverage.xml` can be imported.

Configure these values in the GitHub repository settings:

| Setting | Kind | Value |
| --- | --- | --- |
| `SONAR_ORGANIZATION` | Actions variable | SonarQube Cloud organization key |
| `SONAR_PROJECT_KEY` | Actions variable | SonarQube Cloud project key |
| `SONAR_TOKEN` | Actions secret | Token allowed to analyze this project |

The Sonar job is enabled only when both Actions variables are present. This
keeps the initial rollout safe while the external project and token are being
configured. A missing token after enabling the variables is a configuration
error and should be fixed before merging.

## Workflow behavior

- `ci.yml` runs Ruff, pytest, coverage, and Pyright for Python 3.10 through
  3.14. The Python 3.13 job installs the optional VTracer dependency so the
  complete test suite remains covered.
- `build.yml` validates package distributions, the Windows standalone
  executable, and the vectorize integration path.
- `sonarqube.yml` uses Python 3.13, installs the development and vectorize
  extras, generates `coverage.xml`, and runs
  `SonarSource/sonarqube-scan-action@v7` with a full Git checkout. The scanner
  waits for the Quality Gate and fails the job when the gate fails.
- The Sonar workflow runs on `main` pushes, manual Sonar workflow dispatches,
  and pull requests from branches in this repository. Fork pull requests keep
  the normal checks but skip Sonar so a repository secret is never exposed to
  untrusted code.
- `release.yml` remains separate and is triggered only by version tags.

The scanner configuration lives in [`sonar-project.properties`](../sonar-project.properties).
The GUI remains part of Sonar source analysis, but is excluded from the
coverage percentage because its event loop is an interactive boundary.

### S8707 disposition for issue #52

The Python `pythonsecurity:S8707` rule is intended to catch path injection in
agentic workflows. The issue #52 review snapshot (Sonar analysis
`37961595-155b-459a-94e6-f9baee3b2dc5`) contained three open findings from the
same rule:

| Sonar issue | Location | Reported sink | Disposition |
| --- | --- | --- | --- |
| `AaCZij63wC-YvzveLLyz` | `src/svgconverter/converter.py:210` | `os.replace(staged_output, destination)` | Accept design choice |
| `AaCZij4vwC-YvzveLLyx` | `src/svgconverter/embed.py:113` | `source.read_bytes()` | Accept design choice |
| `AaCZij63wC-YvzveLLyy` | `src/svgconverter/converter.py:192` | `destination.parent.mkdir(...)` | Accept design choice |

These findings are not an unreviewed path flow. SVGConverter is a local
CLI/library and does not accept HTTP requests or run an agent, so its default
caller-selected paths are intentional. Integrations that do accept untrusted
path values must pass `allowed_root` (or the CLI's `--allowed-root`); the
converter resolves candidates and rejects input, output, and symlink paths
outside the configured directory. Making that boundary mandatory would break
the public local API contract.

When these findings are present in SonarQube Cloud, mark each one as
`Accepted` with this rationale:

> SVGConverter is a local CLI/library with no HTTP or agent boundary. Caller-selected paths are intentional for the default local API. Untrusted integrations must use `allowed_root`/`--allowed-root`, which resolves and confines input, output, and symlink paths. Requiring this option by default would break the public API contract; this is an accepted design choice, not an unexplained path flow.

Do not use `//NOSONAR` or a source exclusion for these findings. After the
next `main` analysis, verify that the disposition is retained and that no new
unexplained S8707 finding appears.

### S8707 review for the 1.8.2 preparation

The 2026-10-12 `main` analysis at `26a80e3` reports six open S8707 issues. The following table records the reviewed design-choice dispositions; the live Sonar issue status must be verified separately before release.

| Sonar issue | Reviewed operation | Disposition |
| --- | --- | --- |
| `AaEt3FGRhdzSzw-MMPzx` | Windows exclusive `os.rename` in `_publication.py` | Accept design choice |
| `AaEt3FGRhdzSzw-MMPzw` | Non-replacing `os.link` in `_publication.py` | Accept design choice |
| `AaCZij63wC-YvzveLLyy` | Output parent creation in `converter.py` | Accept design choice |
| `AaCZij63wC-YvzveLLyz` | Explicit overwrite publication in `converter.py` | Accept design choice |
| `AaEsMRl8BIquHGRjpPw2` | Original raster read without preprocessing in `embed.py` | Accept design choice |
| `AaEsMRl8BIquHGRjpPw1` | Original raster read when preprocessing is unnecessary in `embed.py` | Accept design choice |

All six paths originate in the caller-selected local CLI/library input and output arguments. `convert_file_with_metrics()` resolves the optional `allowed_root` and validates both input and explicit output before raster reads or output creation. Its temporary output is created beside the validated destination and is passed directly to publication. Batch conversion propagates the same root. The project has no HTTP or LLM execution boundary; an LLM caller must configure the documented root just like any other untrusted integration. The existing traversal and symlink escape tests verify this contract. `allowed_root` is a path-scope check, not a sandbox against another process changing the filesystem during conversion.

Retain the rule and the Quality Gate. Record these issue-specific dispositions in SonarQube Cloud after review instead of excluding paths or changing the default local API.

## Baseline rollout

1. Run the first scan on `main` and confirm that `coverage.xml` appears in the
   SonarQube Cloud project. Use the SonarQube Cloud workflow's manual dispatch
   when rerunning only the analysis is useful.
2. Review reliability, security, maintainability, duplication, and coverage
   findings. Apply only justified source, test, or generated-artifact
   exclusions.
3. Keep the default Quality Gate non-required while the baseline is reviewed.
4. Open a small same-repository pull request and confirm that the Quality Gate
   result is reported on GitHub.
5. After the result is stable, decide whether to add the Sonar check to branch
   protection. This is a repository setting, separate from the workflow.
6. Add the Quality Gate and coverage badges to both READMEs only after the
   project key and dashboard URLs have been verified.

## Local coverage report

The report can be reproduced locally with:

```bash
pytest --cov=svgconverter \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml
```

`coverage.xml` is ignored by Git and should not be committed.
