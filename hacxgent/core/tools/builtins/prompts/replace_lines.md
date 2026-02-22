# replace_lines

Surgically replace a range of lines in a file.

## Usage

Use `replace_lines` for **high-precision edits**. It is more context-efficient than `search_replace` because you specify exact line numbers:
1. First, use `file_meta` or `read_file` to find the exact line range for your change.
2. Use `replace_lines` to swap those lines with your new content.
3. This is the **PREFERED** tool for large file edits as it minimizes token usage.

## Parameters

- `file_path`: Path to the file to modify.
- `start_line`: 1-based starting line number (inclusive).
- `end_line`: 1-based ending line number (inclusive).
- `new_content`: The replacement content.

## Example

```json
{
  "file_path": "utils.py",
  "start_line": 45,
  "end_line": 50,
  "new_content": "def new_function():
    return "updated""
}
```
