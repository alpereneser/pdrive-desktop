# Contributing to PDrive Desktop

Thank you for helping improve Proton Drive support on Linux.

## Before opening a pull request

1. Discuss substantial behaviour or architecture changes in an issue first.
2. Keep credentials, access tokens, account data, file names, and personal paths out of
   commits, tests, screenshots, logs, and issue reports.
3. Preserve the dependency direction: presentation → application → domain. Infrastructure
   implements application ports; domain code never imports GTK or subprocess APIs.
4. Add or update tests for behavioural and security-sensitive changes.
5. Run `pytest`, `ruff check .`, and `mypy` before submitting.

## Security boundaries

- Never handle the Proton password in this application.
- Never invoke the Proton CLI through a shell.
- Never add telemetry, analytics, advertising, or a PDrive backend.
- Destructive remote actions must be explicit and confirmed.
- Downloads and updates must fail closed when integrity verification fails.

Do not report vulnerabilities in a public issue. Follow [SECURITY.md](SECURITY.md).

