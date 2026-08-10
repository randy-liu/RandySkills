import argparse
import sys

# =============================================================================
# 輸出編碼
# =============================================================================
# Windows 主控台預設為 cp950（繁中）等非 UTF-8 編碼，編不出本腳本輸出的「³」，
# 會在進階診斷的計算式那行拋 UnicodeEncodeError。
# ⚠️ 崩潰點在 Ratio 印出「之後」——外觀上像正常跑完，實則兩項進階診斷全缺，
#    極易被誤判為「該竿沒有觸發診斷」。故在此強制把輸出串流切為 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    # Python < 3.7，或串流已被替換為不支援 reconfigure 的物件（如管線包裝）時略過。
    pass

# =============================================================================
# 判定閾值
# =============================================================================
# 錐度比例 band —— 沿用原始設定，未變更。
RATIO_EX_FAST = 10.0
RATIO_FAST = 7.5
RATIO_REGULAR = 7.0

# 進階診斷閾值
# ⚠️ 以下兩個閾值係由 12 支 DAIWA HEARTLAND 竿的實測樣本歸納而來，屬「暫定值」。
#    樣本數不足以視為定論，僅作為「提醒人工複核」用，不得據以推翻官方調性標示。
BUTT_OVERCAP_FLAG = 100.0   # 元端過剩指數
SLIM_BUTT_FLAG = 8.5        # 元徑 (mm)

SEP = "-" * 30


def classify_ratio(ratio):
    """回傳 (判定文字, 說明文字, 是否落在已知的警示區間)。"""
    if ratio >= RATIO_EX_FAST:
        return (
            "極端高錐度 (EX-Fast)",
            "通常出現在微物竿或特殊底棲特化竿。",
            False,
        )
    if ratio >= RATIO_FAST:
        return (
            "Fast (先調子)",
            "彎曲點集中於前端，中肚具備高支撐力。",
            False,
        )
    if ratio < RATIO_REGULAR:
        return (
            "Regular / Slow (胴調子)",
            "粗細過渡平緩，受壓時均勻向後彎曲。",
            False,
        )
    return (
        "中庸錐度 (Moderate Fast)",
        "介於 Fast 與 Regular 之間，具備適中的彎曲過渡。",
        True,
    )


def print_band_caution():
    """7.0 <= ratio < 7.5 區間的已知校準落差提醒。

    校準樣本來源（刻意不印出：輸出會直接進報告，帶入特定系列的型號會污染
    其他系列的分析，違反 SKILL.md 守則 3）——
        ・802MHRB-21  Ratio 7.17  官方 R
        ・722LRSB-24  Ratio 7.23  官方 R
    型號明細見 references/daiwa_heartland_features.md「腳本校準樣本」。
    """
    print("")
    print("⚠️  【判定可信度提醒：本區間存在已知落差】")
    print("    實測樣本中，落在 7.0〜7.5 區間的釣竿，官方調性字母**皆標示為 R (Regular)**，")
    print("    與本腳本的「中庸錐度」判定不一致。已知案例：")
    print("      ・Ratio 7.17  官方 R")
    print("      ・Ratio 7.23  官方 R")
    print("    → 若該竿有官方調性字母，請**以官方字母為準**，並在報告中說明此落差。")
    print("    → 樣本僅 2 筆，尚不足以調整 band 邊界，故判定文字維持不變。")


def run_diagnostics(tip, butt, length, max_lure):
    """進階診斷。length 單位 m、max_lure 單位 g。任一為 None 則不執行。"""
    print("")
    print("=" * 60)
    print("進階診斷 (Advanced Diagnostics)")
    print("=" * 60)

    if length is None or max_lure is None:
        print("未啟用。")
        print("提示：加上 --length <全長 m> 與 --max-lure <負載上限 g> 可執行下列檢查——")
        print("      ・元端過剩指數（元端是否根本不參與作動）")
        print("      ・全體纖細判定（高錐度比是否為假象）")
        print("      此兩項檢查專門捕捉「兩點式錐度比」看不見的失效情況。")
        return

    # -------------------------------------------------------------------------
    # 診斷 1：元端過剩指數 (Butt Over-Capacity Index)
    # -------------------------------------------------------------------------
    # 原理：元端抗彎能力 ∝ 元徑³（截面模數）；元端所受根部彎矩 ∝ 負載 × 全長。
    #       兩者相除即為「元端相對於其設計負載的餘裕程度」。
    #       數值極高 = 元端在整個設計工作範圍內都不會被撓曲 = 對「彎曲點在哪」毫無貢獻，
    #       但它仍被計入錐度比的分母，因而把 Ratio 灌高、造成 Fast 的假象。
    index = (butt ** 3) / (max_lure * length)
    print("")
    print("[診斷 1] 元端過剩指數 (Butt Over-Capacity Index)")
    print(f"    計算式：元徑³ ÷ (負載上限 × 全長) = {butt}³ ÷ ({max_lure} × {length})")
    print(f"    指數 = {index:.1f}")

    if index >= BUTT_OVERCAP_FLAG:
        print("")
        print(f"    🔴 **警示：指數 ≥ {BUTT_OVERCAP_FLAG:.0f}，元端相對於設計負載過度強壯。**")
        print("        本竿元端在整個設計負載範圍內極可能**永遠不會被撓曲**。")
        print("        → 錐度比的分母端不參與作動，**Ratio 被灌高，Fast 判定不可信**。")
        print("        → 實際彎曲行為應由前段的錐度分佈決定，請以官方調性字母為準。")
        # 校準樣本為 722LRS-21；型號刻意不印出，理由同 print_band_caution()。
        print("        → 已知案例：指數 154.6、Ratio 8.50 判 Fast，官方標 R。")
    else:
        print(f"    ✅ 正常範圍（警示門檻 {BUTT_OVERCAP_FLAG:.0f}）。元端會參與作動，Ratio 判定具參考性。")

    # -------------------------------------------------------------------------
    # 診斷 2：全體纖細判定 (Slim-Blank Check)
    # -------------------------------------------------------------------------
    # 原理：錐度比是「相對值」，看不到兩端的絕對尺寸。
    #       若元徑本身極細，即使 Ratio 很高，中後段也不可能形成「硬棒」，
    #       此時 Fast / EX-Fast 的判定會嚴重誤導。
    print("")
    print("[診斷 2] 全體纖細判定 (Slim-Blank Check)")
    print(f"    元徑 = {butt}mm（門檻 {SLIM_BUTT_FLAG}mm）")

    if butt < SLIM_BUTT_FLAG:
        print("")
        print(f"    🔴 **警示：元徑 < {SLIM_BUTT_FLAG}mm，竿身兩端的絕對尺寸都極小。**")
        print("        高錐度比在此**不代表**「前軟後硬」，而是「前段細到不成比例」。")
        print("        → 中後段同樣缺乏絕對剛度，實際行為是**整支一起彎**，而非彎曲點集中前端。")
        print("        → EX-Fast / Fast 判定在此屬誤導，請以官方調性字母為準。")
        # 校準樣本為 702UL+FS-ST23；型號刻意不印出，理由同 print_band_caution()。
        print("        → 已知案例：元徑 7.4mm、Ratio 10.57 判 EX-Fast，官方標 F。")
    else:
        print("    ✅ 正常範圍。元徑具備足夠的絕對剛度，Ratio 判定具參考性。")

    # -------------------------------------------------------------------------
    print("")
    print(SEP)
    print("⚠️  診斷閾值取自 12 支樣本，屬暫定值。診斷結果僅供「提醒人工複核」，")
    print("    **不得用於推翻官方調性標示，亦不得作為材質推演的依據。**")
    print("    材質造成的調性落差（如 X45 / 3DX 提升響應速度）屬 Step 2 職責，本腳本不處理。")


def main():
    parser = argparse.ArgumentParser(
        description="釣竿幾何錐度運算 (Taper Ratio Calculation)"
    )
    parser.add_argument("--tip", type=float, required=True, help="先徑 (Tip Dia) in mm")
    parser.add_argument("--butt", type=float, required=True, help="元徑 (Butt Dia) in mm")
    parser.add_argument(
        "--length",
        type=float,
        default=None,
        help="全長 (m) — 選填。與 --max-lure 並用可啟用進階診斷",
    )
    parser.add_argument(
        "--max-lure",
        type=float,
        default=None,
        help="路亞負載上限 (g) — 選填。與 --length 並用可啟用進階診斷",
    )

    args = parser.parse_args()

    if args.tip <= 0:
        print("錯誤：先徑必須大於 0")
        sys.exit(1)
    if args.butt <= 0:
        print("錯誤：元徑必須大於 0")
        sys.exit(1)
    if args.length is not None and args.length <= 0:
        print("錯誤：全長必須大於 0")
        sys.exit(1)
    if args.max_lure is not None and args.max_lure <= 0:
        print("錯誤：負載上限必須大於 0")
        sys.exit(1)

    ratio = args.butt / args.tip

    # ---- 基本輸出（格式與舊版一致，確保既有報告可比對）----
    print(f"輸入數值: 先徑(Tip)={args.tip}mm, 元徑(Butt)={args.butt}mm")
    print(f"錐度比例 (Ratio) = {ratio:.2f}")
    print(SEP)

    verdict, note, is_caution_band = classify_ratio(ratio)
    print(f"物理結構判定：{verdict}")
    print(f"說明：{note}")

    if is_caution_band:
        print_band_caution()

    run_diagnostics(args.tip, args.butt, args.length, args.max_lure)


if __name__ == "__main__":
    main()
