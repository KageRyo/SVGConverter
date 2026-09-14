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
  `SonarSource/sonarqube-scan-action@v7` with a full Git checkout.
- The Sonar workflow runs on `main` pushes, manual Sonar workflow dispatches,
  and pull requests from branches in this repository. Fork pull requests keep
  the normal checks but skip Sonar so a repository secret is never exposed to
  untrusted code.
- `release.yml` remains separate and is triggered only by version tags.

The scanner configuration lives in [`sonar-project.properties`](../sonar-project.properties).
The GUI remains part of Sonar source analysis, but is excluded from the
coverage percentage because its event loop is an interactive boundary.

The Python `pythonsecurity:S8707` rule is intended to catch path injection in
agentic workflows. SVGConverter itself is a local CLI/library and does not
accept HTTP requests or run an agent, so its normal caller-selected paths are
not treated as a remote attack surface. Integrations that do accept untrusted
path values should pass `allowed_root` (or the CLI's `--allowed-root`), which
resolves candidates and rejects input, output, and symlink paths outside the
configured directory. Review the remaining baseline finding in SonarQube Cloud
against the actual deployment boundary before changing its disposition; do
not use a source exclusion to hide a new path flow.

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
