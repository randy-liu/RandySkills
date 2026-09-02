---
name: rod-curve-generator
description: >-
  Parses fishing rod Markdown analysis reports to extract geometric parameters 
  and plots realistic ZENAQ-style progressive bending curves using a physical 
  taper power-law engine.
---

# Rod Bending Curve Generator

## Overview
This skill processes fishing rod analysis reports (Markdown) to extract basic specifications (Tip Diameter, Butt Diameter, Lure Rating, Taper Action) and generates realistic progressive load bending curves and comparison charts using a large-deflection cantilever solver over a tapered compliance profile.

🔴 **柔度用的是 `1/d⁴`，而且那個指數是「實測擬合出來的有效值」，不是物理推導。**
（此處原本寫 `I ∝ D^3`，那是 CCS 校準之前的舊值。）最誘人的推導「壁厚 ∝ 直徑 ⇒ `I ∝ d⁴`」
**已被本 repo 的資料否證**——由官方公佈的空白竿身自重反推壁厚，`t/d` 與元徑的相關係數是 −0.765。
不得在任何地方把它寫成物理事實。詳見 `references/ccs_calibration.md` §3-3。

輸入來源是 `rod-spec-decrypter` 產出的 `<型號>_分析報告.md`——**檔名是兩個 skill 之間的契約**，改檔名會讓 `extract` 找不到檔案。

握把長度（不參與彎曲的那一段）另外來自 `references/measured_grip_lengths.md`，
由 `rod-grip-measurer` 量測並寫入。**沒量過的竿款會警告、圖上標「未量測」、且不套用握把剛性**——
那是正確行為，不得用估計值頂替。

## Dependencies
- **uv**: This skill relies on the `uv` skill (from the science plugin) to manage Python dependencies (`matplotlib`, `numpy`) in a clean, isolated environment.
  ⚠️ `uv` 屬**外部相依**，不隨本 repo 安裝。若環境沒有 `uv`，先問使用者要不要改用已裝好 `numpy` / `matplotlib` 的直譯器執行，不要自行 pip install 汙染全域環境。

## 🔴 資料誠實守則（先讀這一條）

本 skill 的產出是**會被拿去跟官方型錄對照的圖**。圖上印錯一個數字，錯的看起來會是型錄。

- **欄位只有兩種狀態**：從報告解析到，或標成「報告未提供」。**沒有第三種**。
- **腳本不會替你補值**。缺全長／先径・元径／ルアー重量時，該份報告會被跳出並列為失敗。
- **不得為了讓圖畫得出來而修改腳本、放寬檢查或手改 JSON**。缺資料就是回去補報告。
- 圖上的 `[Model Parameters]` 區塊是**繪圖用推估值**，不是原廠數據，不得在對話中把它講成規格。
- **曲線的「形狀」有答案卷可以對，「撓曲量」沒有。** 形狀已對照 21 支公佈 CCS Action Angle
  的空白竿身校準（RMS 4.5°）；但撓曲的**絕對公分數**逐支散佈達 ×/÷ 1.32，**不得拿去對照實測**。
  講圖時可以說「這支比那支彎得更靠前」，**不可以**說「掛 5g 會沉 20 公分」。
- 🔴 **這是靜態掛重圖，畫不出動態特性。** 依技術字典，`3DX` 買到的是「形狀復原力、回彈極快」、
  `X45` 買到的是「防止扭轉變形」——**兩者都不改變靜態掛重時的形狀**。所以搭載這類技術的竿，
  實際手感會比圖上「更快」，那個差額是圖在物理上就畫不出來的。圖上已印有固定聲明，
  **在對話中講圖時也必須一併講明**，否則讀者會把「圖上比較慢」讀成「這支竿比較慢」。

## 🔴 改動曲線引擎前必讀

`scripts/rod_curve_cli.py` 的柔度定律（指數、上限、冪次映射、正規化分母、gamma、FORCE_SCALE）
**彼此互相綁定**，動一個就會牽動其他。改完**必須**跑回歸測試：

```bash
python <skill_dir>/scripts/validate_ccs.py
```

它會拿引擎去考 21 支已公佈 Action Angle 的空白竿身，兩道門檻都要過：
**RMS ≤ 5°**，且**模型跨距 ≥ 實測跨距的 55%**。

⚠️ **跨距那道門檻不是多餘的。** 改版前的引擎相關係數有 +0.538 看似不差，但跨距只有 1.6°
（實測 14.0°）——它把每支竿都畫成同一個形狀，只是平均而言錯得一致。**只看 RMS 或相關係數抓不到。**

🔴 **不得為了通過而放寬門檻。** 資料來源、量測協定與每一條結論的推導見
`references/ccs_calibration.md`；該檔第 6 節記錄了**已窮盡的查證途徑**，別再重跑。

### 🔴 改完參數規則，一定要重跑 `extract`——不能只重畫

`derive_curve_parameters()`（起彎點、`k_power`、竿先／元端乘數）是在 **`extract` 階段**執行的，
結果被寫死進 `extracted_rod_data.json` 的 `curve_plotting_parameters`。
`plot-zenaq` 與 `plot-engineering` **只是讀那份 JSON**，不會重新推導。

→ 所以只改 `derive_curve_parameters()` 然後直接重畫，**圖不會變**（或只變一半），
　 而且圖上 `[Model Parameters]` 印的還是舊值——看起來像修改沒生效，其實是資料沒更新。

**正確順序永遠是**：改程式 → `validate_ccs` → **`extract`** → `plot-zenaq` → `plot-engineering`。

⚠️ 反之，改 `build_compliance()`／`solve_bending()`／`FORCE_SCALE` 這類**繪圖時才用到**的東西，
重畫即可，不必重跑 `extract`。分界線是「這個值有沒有被寫進 JSON」。

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
Reads the extracted JSON file and outputs horizontal Engineering-style PNG curves. These plots start horizontally (0 degrees) and include a detailed specification info box on the right.

⚠️ 負載階梯**與 `plot-zenaq` 完全相同**（依該竿額定推演，見 `get_dynamic_load_list()`），兩張圖的差別**只在持竿角度**。
→ 但**同一支竿同一負載，兩張圖的彎曲量本來就不會一樣，這不是 bug**：垂直負載的力臂是竿身的**水平投影**。水平持竿起始力臂是全長，越彎越短（自我煞車）；45 度上舉起始只有 0.707 倍全長，但越彎越長（自我放大）。兩者回授方向相反，所以差距隨負載變化、甚至會變號。**兩張圖不可互相對照數值。**
```bash
uv run <skill_dir>/scripts/rod_curve_cli.py plot-engineering --input <FILE.json> --output-dir <DIR>
```

⚠️ **兩個 plot 指令都會在 `--output-dir` 底下再開一層同名子目錄**（`Progressive_Curves/`、
`Engineering_Curves/`）。要圖落在 `X/Progressive_Curves/` 就傳 `--output-dir X`，
**不是** `--output-dir X/Progressive_Curves`——那會得到 `X/Progressive_Curves/Progressive_Curves/`。

### `validate_ccs`
彎曲形狀的回歸測試。不吃報告、不畫圖，只拿引擎去考公佈的 CCS Action Angle。
**每次改動柔度定律都必須跑**（見上方「改動曲線引擎前必讀」）。
```bash
python <skill_dir>/scripts/validate_ccs.py
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
