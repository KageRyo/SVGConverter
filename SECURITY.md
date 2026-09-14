# Security Policy

## Supported versions

Security fixes are applied to the latest released version of SVGConverter.

## Filesystem path boundary

SVGConverter is a local CLI and library. Its default behavior intentionally
allows the caller to select existing input files and output locations, so it
does not provide a sandbox when `allowed_root` is omitted.

Applications that pass paths from an untrusted user, HTTP request, automation
agent, or other external source should set `allowed_root` (or the CLI's
`--allowed-root`). SVGConverter resolves the configured root and candidate
paths, rejects paths outside the root, and rejects symlink paths that resolve
outside it. The boundary applies to both input reads and output directory/file
writes.

This option is a path-scope control, not a general resource limit. Integrations
should still apply authentication, file-size limits, timeouts, and operating
system permission isolation appropriate to their threat model.

## Reporting a vulnerability

Please do not disclose suspected security vulnerabilities in public GitHub
issues. Use GitHub's private vulnerability reporting feature for this
repository, or contact the repository owner privately with reproduction steps,
affected versions, and potential impact.
