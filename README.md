# PDrive Desktop

[![CI](https://github.com/alpereneser/pdrive-desktop/actions/workflows/ci.yml/badge.svg)](https://github.com/alpereneser/pdrive-desktop/actions/workflows/ci.yml)
[![License: GPL v3+](https://img.shields.io/badge/License-GPL_v3%2B-blue.svg)](LICENSE)

PDrive Desktop is a security-first, native Linux client built on Proton's official
`proton-drive` CLI. It is currently an early development build and must not be relied on
as the only copy of important data.

## Principles

- Credentials never enter this application's process. Authentication is delegated to the
  official CLI and the operating-system secret store.
- Domain and application code do not depend on GTK, subprocesses, or Proton's CLI format.
- Destructive remote operations are denied by default.
- Every CLI operation uses an argument vector (never a shell), a minimal environment,
  bounded output, and a timeout.
- The official binary is not redistributed. Installation will verify Proton's published
  SHA-512 checksum before activation.
- There is no PDrive server and no telemetry. The runtime talks to Proton only through the
  official CLI; decrypted data remains on the user's device.

## Architecture

The project is a modular monolith with process-ready boundaries:

```text
GTK/libadwaita UI -> application use cases -> domain
                              |
                              v
                    DriveGateway protocol
                              |
                              v
                    official CLI adapter
```

This gives DDD/Clean Architecture isolation without adding localhost HTTP services and
extra attack surface to a single-user desktop application. Transfer workers can later be
moved into a sandboxed process without changing the domain or use cases.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

GTK4 and libadwaita are runtime system dependencies for the graphical shell. Core tests
do not require them.

The current development milestone supports browser authentication, folder navigation,
safe-conflict upload/download, folder creation, and confirmed move-to-trash. Permanent
deletion and bidirectional sync remain disabled until their conflict and recovery tests
are complete.

See [`docs/architecture.md`](docs/architecture.md),
[`docs/threat-model.md`](docs/threat-model.md), and
[`docs/design-language.md`](docs/design-language.md).

## Privacy and independence

PDrive Desktop is an independent community project and is not affiliated with or endorsed by
Proton AG. Proton and Proton Drive are trademarks of their respective owner. Before reporting
a problem, remove account identifiers, personal file names, file contents, and session data.

## Contributing and security

Contributions are welcome under the [GPL-3.0-or-later license](LICENSE). Read
[CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes. Security vulnerabilities must be
reported privately as described in [SECURITY.md](SECURITY.md), never in a public issue.
