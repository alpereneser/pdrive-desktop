# Development roadmap

PDrive Desktop remains an early preview. Items are ordered by safety and dependency, not
by visual appeal.

## Release foundation

- Reproducible Debian package checks in CI.
- Versioned GitHub Releases with SHA-256 manifests.
- Immutable release tags and provenance/signature verification.
- User-controlled update checks followed by explicit privileged installation approval.

## Reliable transfers

- In-memory FIFO transfer queue with bounded concurrency, honest indeterminate progress,
  owned-process cancellation, and explicit retry. Completed in 0.1.3.
- Resumable transfers when the official CLI exposes a stable resume/progress contract.
- Downloads staged in a private directory and atomically committed without overwriting.
- Local-only verification that a completed backup contains every expected remote item,
  with type and file-size checks. Completed in 0.1.3.
- Clear offline, authentication-expired, quota, and rate-limit states.

## Desktop integration

- Notifications for completed or failed background transfers.
- Open local destination and copy remote path actions.
- Search, sorting, pagination, keyboard navigation, and accessibility review.
- Settings and About windows with versions, privacy boundary, and diagnostics export.

## Sync beta prerequisites

- Restrictive SQLite state store with integrity checks and schema migrations.
- Explicit local/remote snapshots and a visible conflict state.
- No silent last-writer-wins and no automatic deletion.
- Crash, power-loss, rename, symlink-race, and large-tree tests.

Mounting Drive as a FUSE filesystem is not planned until the official SDK exposes a stable,
safe contract suitable for it. PDrive Desktop will not extract or reuse Proton session secrets
to bridge unsupported backends.
