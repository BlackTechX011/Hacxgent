# read_lines

Read a specific range of lines from a file.

## Usage

Use `read_lines` for **high-precision inspection**:
1. First, use `file_meta` to find the line range of a specific function or class.
2. Use `read_lines` with those exact line numbers to read only the code you need.
3. This is the **PREFERED** tool for reading large files as it minimizes token usage and keeps your context clean.
4. Note: Indices are 1-based (same as `file_meta` and `replace_lines`).

## Parameters

- `file_path`: Path to the file to read.
- `start_line`: 1-based starting line number (inclusive).
- `end_line`: 1-based ending line number (inclusive).

## Example

```json
{
  "file_path": "src/core/agent.py",
  "start_line": 100,
  "end_line": 150
}
```
