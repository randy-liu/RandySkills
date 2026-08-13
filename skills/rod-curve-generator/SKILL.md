---
name: rod-curve-generator
description: >-
  Parses fishing rod Markdown analysis reports to extract geometric parameters 
  and plots realistic ZENAQ-style progressive bending curves using a physical 
  taper power-law engine.
---

# Rod Bending Curve Generator

## Overview
This skill processes fishing rod analysis reports (Markdown) to extract basic specifications (Tip Diameter, Butt Diameter, Lure Rating, Taper Action) and generates realistic progressive load bending curves and comparison charts using a true physics engine (Taper Power Law $I \propto D^3$).

## Dependencies
- **uv**: This skill relies on the `uv` skill (from the science plugin) to manage Python dependencies (`matplotlib`, `numpy`) in a clean, isolated environment.

## Quick Start
```bash
# 1. Ask the user for permission to use `uv run` if dependencies are a concern.
# 2. Extract JSON data from Markdown files in a directory
uv run rod_curve_cli.py extract --input-dir /path/to/md_files --output /path/to/extracted.json

# 3. Generate ZENAQ-style progressive plots and comparison charts
uv run rod_curve_cli.py plot-zenaq --input /path/to/extracted.json --output-dir /path/to/save_plots

# 4. (Optional) Generate horizontal Engineering-style plots with detailed specifications
uv run rod_curve_cli.py plot-engineering --input /path/to/extracted.json --output-dir /path/to/save_plots
```

## Utility Scripts
The core logic is contained in `scripts/rod_curve_cli.py`, which uses PEP 723 metadata to declare its dependencies. Always run it using `uv run`.

### `extract`
Parses all `*_分析報告.md` files in a directory and outputs a structured JSON file.
```bash
uv run scripts/rod_curve_cli.py extract --input-dir <DIR> --output <FILE.json>
```

### `plot-zenaq`
Reads the extracted JSON file and outputs ZENAQ-style progressive load PNG curves (with dynamic weights) and category comparison charts.
```bash
uv run scripts/rod_curve_cli.py plot-zenaq --input <FILE.json> --output-dir <DIR>
```

### `plot-engineering`
Reads the extracted JSON file and outputs horizontal Engineering-style PNG curves. These plots start horizontally (0 degrees), use a fixed load progression (100g, 250g, 500g, 1000g), and include a detailed specification info box in the lower-left corner.
```bash
uv run scripts/rod_curve_cli.py plot-engineering --input <FILE.json> --output-dir <DIR>
```

## Workflow & Error Handling (Strict Rules)

1. **Environment Check**: Before running the script, check if you can run it via `uv`. If you suspect the user doesn't have `uv` installed, explicitly ask them: "May I use `uv run` to safely execute the drawing script without polluting your global environment?".
2. **Missing Data Handling (CRITICAL)**: If the `extract` command fails (Exit Code 1) because a Markdown file is missing crucial data (e.g., "先徑" or "Lure Rating"), the script will print an explicit error message. **You MUST STOP and ask the user to provide or fix the missing data in the markdown file.** DO NOT attempt to bypass the error by fabricating data or modifying the python script. Wait for the user's manual correction.
3. **Report Generation**: After a successful `plot`, list the generated files to the user and summarize the results briefly.

## Common Mistakes
- Trying to run the script with plain `python` instead of `uv run`. The script requires `numpy` and `matplotlib` which may not be globally installed.
- Continuing to the `plot` command if the `extract` command failed. Always check the exit code.
- Trying to fix missing Lure Ratings yourself. Ask the user for the official spec if it is missing in their markdown report.
