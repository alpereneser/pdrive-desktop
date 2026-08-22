# Privacy promise

PDrive Desktop is local-first and serverless.

## What leaves the device

- Operations explicitly requested by the user, sent by Proton's official CLI directly to
  Proton services.
- The one-time download request for a pinned CLI binary from `proton.me`.

## What does not leave the device

- decrypted file content and filenames
- local folder paths and sync mappings
- account session material
- logs, crash reports, usage events, or device identifiers

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
