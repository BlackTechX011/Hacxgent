# log_watcher

Monitor the tailing output of a log file or background process.

## Usage

Use `log_watcher` for **runtime observability**:
1. Monitor logs from background processes (like `npm start`).
2. Retrieve only the last `n` lines of a log file, keeping your context clean.
3. Detect runtime errors or confirm successful application starts.

## Parameters

- `file_path`: Path to the log file to watch.
- `last_lines`: Number of tailing lines to retrieve (default 100).

## Example

```json
{
  "file_path": "logs/server.log",
  "last_lines": 50
}
```
