# Jobs Feature

## Purpose

Job discovery (FE-02). Searches the backend job
index (`GET /api/v1/jobs/search`) and saves
results into the shared application tracker.

## Behavior

- Search state (query, location, results) is local.
- Saving a role calls the shared `create` mutation
  from `useApplications`, so the tracker Kanban
  updates immediately.
- Per-result saving state prevents double submits.

## Key Exports

- `JobDiscovery({ session, onCreateApplication })`

## Testing

- Covered by backend API tests; the component is
  exercised through the shell.
