# context_snapshot

Manage codebase 'Save Points' (snapshots).

## Usage

Use `context_snapshot` for **safety and recovery**:
1. **Create** a snapshot named "before_refactor" before making major changes.
2. If your plan fails, **Restore** the codebase to that known good state.
3. This is essential for maintaining project integrity during long sessions.

## Parameters

- `action`: "create", "restore", or "list".
- `name`: Name of the snapshot (required for create/restore).

## Example

```json
{
  "action": "create",
  "name": "refactor_start"
}
```
```json
{
  "action": "restore",
  "name": "refactor_start"
}
```
```json
{
  "action": "list"
}
```
