import argparse
import sys

# =============================================================================
# 輸出編碼
# =============================================================================
# 理由同 calculate_taper.py：Windows 主控台預設為 cp950（繁中）等非 UTF-8 編碼，
# 編不出本腳本輸出的「≈」「％」等字元，會在計算式那行拋 UnicodeEncodeError。
# ⚠️ 崩潰點在區塊標題印出「之後」——外觀上像正常跑完，實則該區塊的判讀整段消失，
#    極易被誤判為「該竿沒有觸發判讀」。故在此強制把輸出串流切為 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    # Python < 3.7，或串流已被替換為不支援 reconfigure 的物件（如管線包裝）時略過。
    pass

# =============================================================================
# 🔴 本腳本的權限邊界（務必先讀）
# =============================================================================
# 【感度沒有官方標示可以對照。】
# 錐度判定敢下結論，是因為型號字串裡就寫著原廠標的調性可以對答案（官方 key 六欄）。
# 感度沒有這種東西——官方規格表沒有感度欄位，也沒有任何可對答案的公佈值。
#
# → 因此本腳本【一律不輸出分數、不評分、不排名】。
#   只輸出兩樣不需要對答案就能成立的東西：
#     ① 訊號鏈上「哪一環有問題」
#     ② 每個數字「代表什麼」
# → 本腳本輸出的每一項都是推論，報告中須全段標 🟡。

# =============================================================================
# 判定閾值
# =============================================================================
# 接繼偏心指數
# ─────────────────────────────────────────────────────────────────────────────
# 等分接繼（n 節等長）：仕舞寸法 = 全長 ÷ n + 接繼重疊長度，
#   故指數 = 1 + n × 重疊 ÷ 全長，會【略大於】1.0（重疊佔全長僅數 %）。
# グリップジョイント（接縫緊鄰握把）：長節約佔全長 3/4，指數約 1.5。
# → 1.15 取在兩者之間，且對 1.0 側留有數倍於重疊量的餘裕。
# ⚠️ 本閾值屬【幾何推導】，非實測歸納，亦無官方依據。
JOINT_OFFSET_FLAG = 1.15

# 接繼偏心指數的物理下限
# ─────────────────────────────────────────────────────────────────────────────
# n 節竿的仕舞寸法【至少】等於 全長 ÷ n——收起來不可能短於最長的那一節，
# 而最長的一節必然不短於平均長度。故 指數 = 仕舞寸法 × n ÷ 全長 在數學上恆 ≥ 1.0。
# 低於 1.0 必為資料錯誤，最常見的是 --collapsed 誤填 m 而非 cm。
# ⚠️ 不擋這一項的話，單位填錯會算出 0.0x，落進「< 1.15」而被印成 ✅ 等分接繼——
#    這是【靜默誤判】：外觀上正常跑完，結論卻完全相反。
# 0.98 是替官方數值的四捨五入留的容差（仕舞寸法標到整數 cm、全長標到 0.01m）。
JOINT_IMPOSSIBLE_FLOOR = 0.98

# 負載跨度（上限 ÷ 下限）
# ─────────────────────────────────────────────────────────────────────────────
# ⚠️ 本閾值【無任何實測、統計或官方依據】，純為觸發人工複核之用。
#    不得據以否定官方標示的負載範圍，也不得反推該竿「設計不良」。
LOAD_SPAN_WIDE = 5.0

SEP = "-" * 30


def block_joint(length, pieces, collapsed_cm):
    """[鏈路] 接繼位置。length 單位 m、collapsed_cm 單位 cm。"""
    print("")
    print("[鏈路 1] 接繼位置 (Joint Position)")

    if length is None or pieces is None or collapsed_cm is None:
        print("    未提供 → 不判讀。")
        print("    提示：需同時帶入 --length <全長 m>、--pieces <継数>、--collapsed <仕舞寸法 cm>。")
        return

    # -------------------------------------------------------------------------
    # 1 節竿特判
    # -------------------------------------------------------------------------
    # 1 節竿的 仕舞寸法 ≈ 全長、継数 = 1，代入公式同樣得到 ≈1.0，
    # 與「中央對切二節」【完全同值】。若不特判，會把一支根本沒有接縫的竿
    # 講成「接縫落在竿身中段、正處於震動路徑上」——結論剛好相反。
    if pieces == 1:
        print("    継数 = 1 → 本竿無接繼，不套用接繼偏心指數。")
        print("")
        print("    ✅ 訊號鏈上不存在「接縫」這個斷點。")
        print("        接縫是剛性不連續處，會反射並吸收高頻震動；沒有接縫就沒有這項損失。")
        print("    → Step 4 的訊號鏈判定中，「接繼」這個環節標【不適用（無接繼）】。")
        print("      🔴 **不得標「未知」**——標未知會誤觸「有未知環節即不得下定論」的規則，")
        print("         把一個已知的有利條件寫成資料缺口。這裡是已知，且是好消息。")
        return

    collapsed = collapsed_cm / 100.0

    if collapsed >= length:
        print(f"    🔴 資料矛盾：仕舞寸法 {collapsed_cm}cm ≥ 全長 {length}m，但継数 = {pieces}。")
        print("        請確認單位（--collapsed 為 cm、--length 為 m）與數值來源後重跑。不判讀。")
        return

    # -------------------------------------------------------------------------
    # 原理：接縫位置決定它落在震動路徑的哪一段。
    #       仕舞寸法 × 継数 即「把各節攤平後的總長」，除以全長即得各節長度的均勻程度。
    #       等分 → 商 ≈ 1.0（接縫落在竿身中段）；某節特別長 → 商顯著大於 1.0。
    # -------------------------------------------------------------------------
    index = collapsed * pieces / length
    print("")
    print(f"    計算式：仕舞寸法(m) × 継数 ÷ 全長(m) = {collapsed:.2f} × {pieces} ÷ {length}")
    print(f"    接繼偏心指數 = {index:.2f}")

    if index < JOINT_IMPOSSIBLE_FLOOR:
        print("")
        print("    🔴 **資料矛盾：指數低於物理下限 1.0。**")
        print(f"        {pieces} 節竿的仕舞寸法至少等於 全長 ÷ {pieces}，故指數不可能小於 1.0。")
        print("        最常見的原因是 --collapsed 誤填成 m（應為 cm）。")
        print("        請確認數值來源後重跑。**不判讀。**")
        return

    if index >= JOINT_OFFSET_FLAG:
        print("")
        print(f"    🔴 **指數 ≥ {JOINT_OFFSET_FLAG}：某一節明顯長於等分，接縫偏離竿身中段。**")
        print("        ⚠️ 但本指數【分辨不出接縫偏向竿先端還是握把端】——")
        print("           長節是竿先段或元段，兩者算出來是同一個數。")
        print("           → 報告若要指出方向，**必須寫明那是假設**，不是本指數算出來的。")
    else:
        print("")
        print(f"    ✅ 指數 < {JOINT_OFFSET_FLAG}：各節長度接近等分，接縫落在竿身中段附近。")
        print("        中段正在震動傳導路徑上，此處的接繼剛性直接決定高頻能不能通過。")

    print("")
    print("    ⚠️ 本指數為【近似值】：仕舞寸法含握把、且接繼處有重疊長度，")
    print("       故等分接繼的實際落點會略高於 1.0，而非正好 1.0。")
    print("")
    print("    🔴 **官方規格表有 `ジョイント仕様` 欄位，直接寫明接繼形式。**")
    print("       該欄若有提供，**一律以官方欄位為準**，本指數僅供佐證——")
    print("       本指數是從仕舞寸法回推的結果（🟡），官方欄位是明文（🟢）。")
    print("    → 接繼技術對此環的實際影響，須依守則 4 查技術字典，本腳本不處理。")


def block_blank_material(carbon_pct):
    """[鏈路] blank 材料。carbon_pct 單位 %。"""
    print("")
    print("[鏈路 2] blank 材料 (Blank Material)")

    if carbon_pct is None:
        print("    未提供 → 不判讀。")
        print("    提示：加上 --carbon-pct <カーボン含有率 %> 可判讀 blank 內有無非碳材料。")
        return

    print(f"    カーボン含有率 = {carbon_pct}％")

    # -------------------------------------------------------------------------
    # 原理：震動在材料中傳遞時，能量會被材料的內部阻尼轉成熱而衰減。
    #       碳纖維阻尼低（傳得遠），玻璃纖維與樹脂阻尼高（吃掉震動）。
    #       故非碳成分的有無，是 blank 這一環的傳導能力的方向性指標。
    # -------------------------------------------------------------------------
    if carbon_pct >= 100:
        print("")
        print("    ✅ 100％ → blank 不含非碳材料。")
        print("        沒有玻璃纖維這類高阻尼材料在中途吃掉震動。")
    else:
        non_carbon = 100.0 - carbon_pct
        print("")
        print(f"    🔴 **未達 100％ → blank 內含 {non_carbon:g}％ 的非碳材料。**")
        print("        非碳材料（玻纖、芳綸，或較多的樹脂）阻尼高，會吸收震動、削弱傳導。")
        print("        ⚠️ 但本數字【不指出非碳材料在哪裡】：可能分佈於全長，")
        print("           也可能只是局部補強（導環固定處、竿先等）。")
        print("           **兩種假說併存，無法從百分比分離**，報告中須照實講明。")

    print("")
    print("    ⚠️ **DAIWA 未公開此百分比的量測基準**——")
    print("       是「碳 vs 玻纖」，還是「纖維 vs 樹脂」，官方沒有說明。")
    print("    → 本項【僅可判讀方向，不得量化】。")
    print("       嚴禁寫成「碳含有率高 x％ 所以感度高 y％」這類敘述。")


def block_load_window(min_lure, max_lure):
    """[通道] 荷重讀取窗。單位 g。"""
    print("")
    print("[通道] 荷重讀取窗 (Load Reading Window)")

    if min_lure is None or max_lure is None:
        print("    未提供 → 不判讀。")
        print("    提示：需同時帶入 --min-lure <下限 g> 與 --max-lure <上限 g>。")
        return

    if max_lure <= min_lure:
        print(f"    🔴 資料矛盾：上限 {max_lure}g ≤ 下限 {min_lure}g。請確認後重跑。不判讀。")
        return

    # -------------------------------------------------------------------------
    # 原理：竿先撓曲量與靜態負載成正比。
    #       「感覺得到餌的重量、感覺得到底質變化」靠的是撓曲量落在可辨識的範圍內。
    #       跨度即「同一支竿被要求覆蓋的撓曲量倍數」——倍數越大，兩端越可能落在
    #       可辨識範圍之外。
    # -------------------------------------------------------------------------
    span = max_lure / min_lure
    print("")
    print(f"    計算式：上限 ÷ 下限 = {max_lure} ÷ {min_lure}")
    print(f"    負載跨度 = {span:.1f} 倍")

    if span >= LOAD_SPAN_WIDE:
        print("")
        print(f"    🔴 **跨度 ≥ {LOAD_SPAN_WIDE:.0f} 倍：兩端都難讀。**")
        print("        最輕的一端：竿幾乎不彎，沒有形變可當參考基準，讀不出重量。")
        print("        最重的一端：竿已接近滿載，再多的重量變化也分不出差別。")
        print("        → 荷重感度只在中段兌現，報告須指出「這支竿的重量感落在哪一段餌重」。")
    else:
        print("")
        print(f"    ✅ 跨度 < {LOAD_SPAN_WIDE:.0f} 倍：設計集中，撓曲量在全區間都落在可辨識範圍。")
        print("        荷重感度不挑餌重，全域可讀。")

    print("")
    print(f"    ⚠️ {LOAD_SPAN_WIDE:.0f} 倍這個門檻【無實測、統計或官方依據】，純為觸發人工複核之用。")
    print("       **不得**據以否定官方標示的負載範圍，也不得反推該竿「設計不良」。")


def print_footer():
    print("")
    print(SEP)
    print("⚠️  本腳本只處理數字。材質與技術造成的感度差異屬 Step 4「感度鏈路判定」職責，")
    print("    本腳本不處理，也不得期待它示警。")
    print("")
    print("🔴 **感度沒有官方標示可以對照。**")
    print("    調性判定敢下結論，是因為型號字串裡就寫著原廠標的調性可以對答案；感度沒有這種東西。")
    print("    → 本腳本輸出的每一項都是**推論**，報告中須全段標 🟡，")
    print("      並依 Output Style §5 白話講明「這裡沒有原廠答案可以對，是我推的」。")
    print("    → **嚴禁**把任何一項寫成分數、評分或肯定句。")


def main():
    parser = argparse.ArgumentParser(
        description="釣竿感度鏈路運算 (Sensitivity Chain Calculation)"
    )
    parser.add_argument("--length", type=float, default=None, help="全長 (m) — 選填")
    parser.add_argument("--pieces", type=int, default=None, help="継数 (節數) — 選填")
    parser.add_argument(
        "--collapsed", type=float, default=None, help="仕舞寸法 (cm) — 選填"
    )
    parser.add_argument(
        "--min-lure", type=float, default=None, help="路亞負載下限 (g) — 選填"
    )
    parser.add_argument(
        "--max-lure", type=float, default=None, help="路亞負載上限 (g) — 選填"
    )
    parser.add_argument(
        "--carbon-pct", type=float, default=None, help="カーボン含有率 (%%) — 選填"
    )

    args = parser.parse_args()

    if args.length is not None and args.length <= 0:
        print("錯誤：全長必須大於 0")
        sys.exit(1)
    if args.pieces is not None and args.pieces < 1:
        print("錯誤：継数必須至少為 1")
        sys.exit(1)
    if args.collapsed is not None and args.collapsed <= 0:
        print("錯誤：仕舞寸法必須大於 0")
        sys.exit(1)
    if args.min_lure is not None and args.min_lure <= 0:
        print("錯誤：負載下限必須大於 0")
        sys.exit(1)
    if args.max_lure is not None and args.max_lure <= 0:
        print("錯誤：負載上限必須大於 0")
        sys.exit(1)
    if args.carbon_pct is not None and not (0 < args.carbon_pct <= 100):
        print("錯誤：カーボン含有率必須介於 0（不含）與 100 之間")
        sys.exit(1)

    print("=" * 60)
    print("感度鏈路運算 (Sensitivity Chain Calculation)")
    print("=" * 60)
    print("本運算【不輸出分數】。感度無官方標示可對照，全部輸出屬推論。")

    block_joint(args.length, args.pieces, args.collapsed)
    block_blank_material(args.carbon_pct)
    block_load_window(args.min_lure, args.max_lure)
    print_footer()


if __name__ == "__main__":
    main()
