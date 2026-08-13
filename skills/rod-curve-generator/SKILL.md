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

輸入來源是 `rod-spec-decrypter` 產出的 `<型號>_分析報告.md`——**檔名是兩個 skill 之間的契約**，改檔名會讓 `extract` 找不到檔案。

## Dependencies
- **uv**: This skill relies on the `uv` skill (from the science plugin) to manage Python dependencies (`matplotlib`, `numpy`) in a clean, isolated environment.
  ⚠️ `uv` 屬**外部相依**，不隨本 repo 安裝。若環境沒有 `uv`，先問使用者要不要改用已裝好 `numpy` / `matplotlib` 的直譯器執行，不要自行 pip install 汙染全域環境。

## 🔴 資料誠實守則（先讀這一條）

本 skill 的產出是**會被拿去跟官方型錄對照的圖**。圖上印錯一個數字，錯的看起來會是型錄。

- **欄位只有兩種狀態**：從報告解析到，或標成「報告未提供」。**沒有第三種**。
- **腳本不會替你補值**。缺全長／先径・元径／ルアー重量時，該份報告會被跳出並列為失敗。
- **不得為了讓圖畫得出來而修改腳本、放寬檢查或手改 JSON**。缺資料就是回去補報告。
- 圖上的 `[Model Parameters]` 區塊是**繪圖用推估值**，不是原廠數據，不得在對話中把它講成規格。

## Quick Start
```bash
# 1. Ask the user for permission to use `uv run` if dependencies are a concern.
# 2. Extract JSON data from Markdown files in a directory
uv run <skill_dir>/scripts/rod_curve_cli.py extract --input-dir /path/to/md_files --output /path/to/extracted.json

# 3. Generate ZENAQ-style progressive plots and comparison charts
uv run <skill_dir>/scripts/rod_curve_cli.py plot-zenaq --input /path/to/extracted.json --output-dir /path/to/save_plots

# 4. (Optional) Generate horizontal Engineering-style plots with detailed specifications
uv run <skill_dir>/scripts/rod_curve_cli.py plot-engineering --input /path/to/extracted.json --output-dir /path/to/save_plots
```

🔴 **路徑一律用 `<skill_dir>/scripts/...`**。安裝時 `bin/install.js` 會把 `<skill_dir>` 換成實際的絕對路徑；寫成裸檔名或相對路徑，注入到 Copilot／Cursor／Windsurf 之後會找不到腳本。

## Utility Scripts
The core logic is contained in `scripts/rod_curve_cli.py`, which uses PEP 723 metadata to declare its dependencies. Always run it using `uv run`.

### `extract`
Parses all `*_分析報告.md` files in a directory and outputs a structured JSON file.
```bash
uv run <skill_dir>/scripts/rod_curve_cli.py extract --input-dir <DIR> --output <FILE.json>
```

必需欄位（缺一即該份報告失敗）：**全長**、**先径・元径**、**ルアー重量**。
其餘欄位（適合ライン／標準自重／仕舞寸法／種類／調性／竿先結構／材質）解析不到時填 `null`，圖上顯示「報告未提供」。

### `plot-zenaq`
Reads the extracted JSON file and outputs ZENAQ-style progressive load PNG curves (with dynamic weights) and category comparison charts.
```bash
uv run <skill_dir>/scripts/rod_curve_cli.py plot-zenaq --input <FILE.json> --output-dir <DIR>
```
對比圖依「種類」分成 BAITCASTING / SPINNING 兩組。**報告裡沒有種類欄位的竿會被排除於對比圖之外**（腳本會以 `[WARN]` 點名），單竿的漸進圖仍照常產生。

### `plot-engineering`
Reads the extracted JSON file and outputs horizontal Engineering-style PNG curves. These plots start horizontally (0 degrees), use a fixed load progression (100g, 250g, 500g, 1000g), and include a detailed specification info box in the lower-left corner.
```bash
uv run <skill_dir>/scripts/rod_curve_cli.py plot-engineering --input <FILE.json> --output-dir <DIR>
```

## Workflow & Error Handling (Strict Rules)

1. **Environment Check**: Before running the script, check if you can run it via `uv`. If you suspect the user doesn't have `uv` installed, explicitly ask them: "May I use `uv run` to safely execute the drawing script without polluting your global environment?".
2. **Missing Data Handling (CRITICAL)**: `extract` 會**先把能解析的都解析完**，再一次列出所有缺漏，並以 **exit code 1** 結束。
   - 成功的部分仍會寫進 JSON（不必為了一份壞檔重跑全部），但**只要 exit code 是 1，你就必須停下來**，把「哪一份報告缺哪個欄位」原文轉達給使用者，並等待他們補齊。
   - **DO NOT** 憑空補值、**DO NOT** 改腳本繞過檢查、**DO NOT** 拿部分 JSON 直接往下畫圖然後當作全部完成。
3. **Report Generation**: After a successful `plot`, list the generated files to the user and summarize the results briefly. 若腳本印出任何 `[WARN]`（例如某支竿沒有種類欄位、某個分類沒有竿），**必須一併轉達**，不得只報成功。

## Common Mistakes
- Trying to run the script with plain `python` instead of `uv run`. The script requires `numpy` and `matplotlib` which may not be globally installed.
- 用裸檔名或相對路徑呼叫腳本，而不是 `<skill_dir>/scripts/rod_curve_cli.py`。
- Continuing to the `plot` command if the `extract` command failed. Always check the exit code.
- Trying to fix missing Lure Ratings yourself. Ask the user for the official spec if it is missing in their markdown report.
- 把圖上 `[Model Parameters]` 的推估值（起彎點％、Kp 等）講成原廠公佈的規格。
