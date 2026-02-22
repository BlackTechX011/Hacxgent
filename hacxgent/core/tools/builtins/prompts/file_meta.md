# file_meta

Return a structural map of a file (classes, functions, methods) with line numbers.

## Usage

Use `file_meta` as your **FIRST STEP** when encountering a large file (>200 lines). It allows you to:
1. Understand the file's architecture without consuming thousands of context tokens.
2. Identify exact line ranges for specific functions or classes.
3. Determine where to apply surgical edits using `replace_lines`.

## Parameters

- `file_path`: Path to the file to analyze.

## Example

```json
{
  "file_path": "src/main.py"
}
```
