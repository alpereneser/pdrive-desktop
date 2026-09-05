# Privacy promise

PDrive Desktop is local-first and serverless.

## What leaves the device

- Operations explicitly requested by the user, sent by Proton's official CLI directly to
  Proton services.
- The one-time download request for a pinned CLI binary from `proton.me`.

PDrive Desktop has no operator account, API, backend, database, relay, analytics endpoint, or
remote diagnostic collector. Connecting a Proton account creates a session only in Proton's
official CLI and the user's operating-system secret store.

## What does not leave the device

- decrypted file content and filenames
- local folder paths and sync mappings
- account session material
- logs, crash reports, usage events, or device identifiers

PDrive never uploads these items to the project maintainers. A user may still intentionally
upload a local file to their own Proton Drive; in that case the official CLI encrypts and sends
the requested operation directly to Proton.

PDrive itself sends no telemetry. The official Proton CLI contains Proton's own crash and
anonymous operational-metrics implementation and follows the telemetry preference of the
user's Proton account. Those metrics are sent to Proton, not to PDrive; the reviewed
implementation records operational counters rather than file content. Users wanting no
Proton metrics should disable telemetry in their Proton account settings. Future PDrive
functionality that changes this document requires a security review and explicit opt-in.

## Local exposure

End-to-end encryption protects data in transit and at Proton. It cannot hide a file from
software that already controls the user's unlocked computer. Downloads, previews, and
sync state must be handled locally and are therefore protected by normal Linux account,
filesystem, full-disk-encryption, and screen-lock controls.
