# file_operations

Perform file management tasks: delete, move, copy, or create directory.

## Usage

Use `file_operations` for **safe file management**:
1. **Delete**: Remove files or entire directories (requires user permission).
2. **Move**: Rename or relocate files/directories.
3. **Copy**: Create duplicates of files/directories.
4. **Mkdir**: Create new directory structures recursively.
5. Preferred over bash commands like `rm`, `mv`, `cp`, `mkdir` for cross-platform reliability and safety checks.

## Parameters

- `action`: "delete", "move", "copy", or "mkdir".
- `source`: Source path (file or directory).
- `destination`: Destination path (required for move, copy, mkdir).

## Example

```json
{
  "action": "delete",
  "source": "temp_file.txt"
}
```
