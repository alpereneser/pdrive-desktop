# Architecture decisions

## ADR-001: Modular monolith, not network microservices

**Status:** accepted

A desktop client is deployed, upgraded, observed, and trusted as one product. Splitting it
into network services would introduce ports, authentication between local services,
version skew, and more failure modes. We retain microservice-quality boundaries as Python
packages and ports. Long-running transfers may later execute in a separately sandboxed
worker over a narrow Unix-domain socket.

## Bounded contexts

- **Drive Catalog:** remote nodes, navigation, metadata.
- **Transfer:** upload/download jobs and progress.
- **Sync:** mappings, snapshots, conflict policy. Not enabled in the first milestone.
- **Identity:** observes CLI authentication state; it never owns credentials.

Dependencies point inward: UI and infrastructure depend on application/domain contracts;
the domain imports neither.

## Known quality debt

The GTK presentation adapter currently coordinates layout, dialogs, and row interaction
inside one window class. Before the project leaves the 0.1 development series, sidebar,
toolbar, file-list, and dialog construction will be extracted into focused presentation
components. No domain or infrastructure behavior may move into those widgets.

## Error model

Infrastructure errors are translated into typed application errors. Raw CLI stderr is
kept out of user-facing messages until it has been redacted. Commands carry a correlation
ID, but paths and filenames are excluded from normal telemetry.
