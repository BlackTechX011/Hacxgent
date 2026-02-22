# impact_analyzer

Analyze the global impact of modifying a symbol (function, class, variable).

## Usage

Use `impact_analyzer` for **global dependency mapping**:
1. Before renaming or changing a public function or class signature.
2. Find all files and line numbers where the symbol is referenced.
3. This tool ensures you update all call sites, preventing "ripple effect" regressions.

## Parameters

- `symbol`: The symbol name (function/class) to analyze for impacts.
- `ignore_paths`: Paths to ignore (e.g., node_modules, build).

## Example

```json
{
  "symbol": "process_data",
  "ignore_paths": ["node_modules", "dist"]
}
```
