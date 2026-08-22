# Threat model

## Protected assets

- Proton session material held by the OS secret store
- decrypted local files and filenames
- remote file integrity and availability
- local sync database and configuration

## Trust boundaries

The UI and application core trust only validated domain values. The official
`proton-drive` executable is a privileged dependency and must be installed from
`proton.me`, checksum verified, owned by the current user or root, and not group/world
writable. CLI JSON, filesystem events, remote names, and previewed files are untrusted.

## Controls in milestone 1

- browser-based CLI login; no password fields or credential persistence
- `create_subprocess_exec`; never `shell=True`
- fixed command allowlist and validated absolute executable path
- sanitized environment and deterministic locale
- timeouts plus stdout/stderr size limits
- no automatic deletion, overwrite, link following, or file preview execution
- logs redact home paths and never record CLI environment or raw file content
- no PDrive server, analytics SDK, crash uploader, tracking pixel, or PDrive telemetry
- application runtime has no HTTP client; only the pinned installer downloads the official
  CLI and verifies it against an embedded SHA-512 digest

## Privacy data flow

```text
User interface -> local application core -> official proton-drive CLI -> Proton
                                          -> GNOME Keyring (session only)
```

There is no PDrive-operated relay, database, control plane, update server, or analytics
endpoint. The official CLI may send Proton crash/operational metrics according to the
user's Proton account preference; this is disclosed separately. Decrypted names and
content necessarily exist on the user's endpoint while they
are displayed, downloaded, indexed for sync, or uploaded. They never leave the endpoint
except encrypted through the official Proton client. Diagnostic export will be opt-in and
redacted before it is shown to the user; the application will never submit it itself.

## Deferred before sync beta

- atomic downloads into a private temporary file followed by verified rename
- symlink/race protection using directory file descriptors where supported
- SQLite integrity checks and restrictive file permissions
- explicit conflict states; never silent last-writer-wins
- signed release artifacts, SBOM, dependency scanning and reproducible packaging

The application cannot protect decrypted files on a compromised endpoint. Full-disk
encryption, screen locking, timely OS updates, and Proton 2FA remain user controls.
