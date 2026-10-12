# Tracker Feature

## Purpose

Application tracker with a Kanban pipeline
(FE-02, FE-04 Kanban UI).

## Behavior

- Quick-add form creates applications via
  `POST /api/v1/applications`.
- Kanban columns: applied → interview → offer →
  rejected. Cards move with
  `PATCH /api/v1/applications/{id}/status` and
  are removed with `DELETE /api/v1/applications/{id}`.
- Movement uses buttons (not drag-and-drop) so
  every action is keyboard- and screen-reader-
  accessible.
- Data access is owned by the shell via
  `useApplications`, shared with the jobs feature.

## Key Exports

- `ApplicationTracker({ session, applicationsBundle })`
- `KanbanBoard` (internal)

## Testing

- `ApplicationTracker.test.jsx` — column rendering,
  grouping, move/delete mutations, auth guard
