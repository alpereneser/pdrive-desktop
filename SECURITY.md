# Security Policy

## Supported versions

Only the latest published release receives security fixes during early development.

## Reporting a vulnerability

Please use GitHub's **Security → Report a vulnerability** private reporting form for this
repository. Do not include Proton credentials, recovery phrases, session data, personal file
names, or decrypted file contents. A minimal synthetic reproduction is preferred.

Do not open a public issue until a fix is available. Maintainers will acknowledge a valid
report, coordinate remediation, and credit the reporter unless anonymity is requested.

## Trust model

PDrive Desktop has no backend and does not receive Proton passwords. Authentication and
encrypted-drive operations are delegated to Proton's official CLI. See
[docs/threat-model.md](docs/threat-model.md) for the full boundary and limitations.

