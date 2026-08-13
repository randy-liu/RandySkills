# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "numpy",
#     "matplotlib",
# ]
# ///
import argparse
import glob
import json
import math
import os
import re
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# Ensure UTF-8 output encoding.
# 🔴 stderr 也必須一起設定：錯誤訊息是中文，而 Windows 主控台預設 cp950，
#    只設 stdout 會讓「缺哪個欄位」整段變成亂碼——那正是使用者最需要讀懂的一行。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8')

# Ensure fallback fonts for CJK characters
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# ==========================================
# PARSER LOGIC
# ==========================================
# 🔴 鐵則一：每個欄位只有兩種狀態——「從報告裡解析到」或「None」。一律不給預設值。
#    這些圖會被拿去跟官方型錄對照，填一個猜出來的數字等於讓圖說謊。
#    缺少繪圖必需欄位（全長／先径・元径／ルアー重量）的報告，直接列為失敗、
#    不進 JSON，由使用者補齊後重跑。
#
# 🔴 鐵則二：廠牌專屬知識（型號後綴、技術名稱）不得寫進本檔。
#    那些屬於 rod-spec-decrypter 的 references/ 字典。寫死在這裡會在換廠牌時
#    無聲算錯，而且字典更新了也不會同步。本檔只認「報告裡實際寫了什麼」。

# 竿先起彎點（佔全長 %）。🟡 這是繪圖用的形狀參數，不是原廠數據——
# 依調性碼的定義排序（X 最靠竿尖、S 最靠握把），僅供決定曲線外形，
# 不得反過來被當成「原廠公佈的彎曲點」。
FLEX_POINT_BY_TAPER = {"X": 30.0, "F": 35.0, "R": 45.0, "S": 55.0}
FLEX_POINT_UNKNOWN = 45.0
SOLID_TIP_FLEX_POINT = 25.0


class ReportParseError(Exception):
    """單一報告缺少繪圖必需欄位。由 do_extract 收集後一次回報，不中斷整批。"""

    def __init__(self, file_name, missing):
        self.file_name = file_name
        self.missing = missing
        super().__init__("{}: missing {}".format(file_name, "、".join(missing)))


def clean_markdown_tags(text):
    if not text: return ""
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = text.replace('**', '').replace('`', '')
    return text.strip()

def clean_text_line(text):
    if not text: return ""
    text = re.sub(r'^\s*#+\s*', '', text)
    text = clean_markdown_tags(text)
    text = re.sub(r'^[>\s\-*•]+', '', text)
    return text.strip()


def parse_lure_max_g(lure_str):
    """取路亞負載上限（g）。取不到一律回傳 None，不給預設值。"""
    if not lure_str:
        return None
    m = re.search(r'([\d\.]+)\s*[〜～~\-–—]+\s*([\d\.]+)\s*g', lure_str)
    if m:
        return float(m.group(2))
    g_matches = re.findall(r'([\d\.]+)\s*g', lure_str)
    if g_matches:
        return max(float(x) for x in g_matches)
    return None


def parse_taper_ratio(clean_content, tip_dia_mm, butt_dia_mm):
    """取粗細比，回傳 (數值, 來源)。

    報告的實際寫法是「粗細比 5.88（屁股 9.4mm ÷ 竿尖 1.6mm）」，
    不是「粗細比（Ratio）＝5.88」。
    🔴 不得全文搜尋裸的「Ratio <數字>」：Step 1 規定報告必須原文引述
       calculate_taper.py 的校準警示，而那段警示裡含有別支竿的
       「・Ratio 7.17　官方 R」「・Ratio 7.23　官方 R」——會抓成這支竿的值。
    """
    number = r'[＝=:：]?\s*([\d\.]+)'
    lines = clean_content.splitlines()

    # 第一順位：報告自己的「粗細比」結論句。
    for line in lines:
        if "粗細比" not in line:
            continue
        m = re.search(r'粗細比\s*(?:[（(]\s*Ratio\s*[）)])?\s*' + number, line)
        if m:
            return float(m.group(1)), "報告"

    # 第二順位：Ratio 字樣，但排除引述進來的校準樣本行。
    for line in lines:
        stripped = line.strip()
        if "Ratio" not in line or "官方" in line or stripped.startswith(("・", "･")):
            continue
        m = re.search(r'Ratio\s*' + number, line)
        if m:
            return float(m.group(1)), "報告"

    # 第三順位：用已解析到的先徑／元徑自行計算。這是粗細比的定義本身，不是猜測。
    return round(butt_dia_mm / max(0.1, tip_dia_mm), 2), "本腳本計算"


def parse_butt_excess(clean_content):
    """取元端過剩指數。取不到回傳 None。

    calculate_taper.py 把標題與數值印在不同行——
        [診斷 1] 元端過剩指數 (Butt Over-Capacity Index)
            計算式：元徑³ ÷ (負載上限 × 全長) = ...
            指數 = 18.1
    所以只掃標題那一行是抓不到的（原本的寫法就抓不到，一律變成 0.0）。
    先看標題行本身有沒有數值，沒有再往下找幾行的「指數 ＝ ◯」。
    """
    lines = clean_content.splitlines()
    for i, line in enumerate(lines):
        if "元端過剩指數" not in line:
            continue
        tail = line.split("元端過剩指數", 1)[1]
        m = re.search(r'([\d\.]+)', tail)
        if m:
            return float(m.group(1))
        for follow in lines[i + 1:i + 6]:
            # 只認「指數 ＝ ◯」；計算式那一行同樣有數字，不能亂抓。
            m = re.search(r'指數\s*[＝=:：]\s*([\d\.]+)', follow)
            if m:
                return float(m.group(1))
        break
    return None


def parse_report_file(file_path):
    """解析單一份分析報告。缺必需欄位時 raise ReportParseError，由呼叫端收集。"""
    with open(file_path, "r", encoding="utf-8") as f:
        raw_content = f.read()
    clean_content = clean_markdown_tags(raw_content)
    file_name = os.path.basename(file_path)
    model_name = file_name.replace("_分析報告.md", "")
    missing = []

    # --- 全長（必需）：曲線的基礎尺度，缺了整張圖都是假的 ---
    m_len = re.search(r'\|\s*全長\s*\|\s*([\d\.]+)\s*m', clean_content)
    length_m = float(m_len.group(1)) if m_len else None
    if length_m is None:
        missing.append("全長")

    # --- 先径・元径（必需）：錐度剖面 ---
    # 官方欄位名是「先径・元径」（中黑點），報告轉寫時可能改成 ／ 或 /，
    # 繁體報告也可能寫成「先徑」，故字形與分隔符都放寬。
    sep = r'[・･/／]'
    m_dia = re.search(
        r'\|\s*先[径徑]\s*' + sep + r'\s*元[径徑]\s*\|\s*([\d\.]+)\s*' + sep + r'\s*([\d\.]+)\s*mm',
        clean_content)
    if m_dia:
        tip_dia_mm, butt_dia_mm = float(m_dia.group(1)), float(m_dia.group(2))
    else:
        # 退一步：先徑與元徑分列兩列的表格
        m_tip = re.search(r'\|\s*先[径徑]\s*\|\s*([\d\.]+)\s*mm', clean_content)
        m_butt = re.search(r'\|\s*元[径徑]\s*\|\s*([\d\.]+)\s*mm', clean_content)
        tip_dia_mm = float(m_tip.group(1)) if m_tip else None
        butt_dia_mm = float(m_butt.group(1)) if m_butt else None
        if tip_dia_mm is None or butt_dia_mm is None:
            missing.append("先径・元径")

    # --- ルアー重量（必需）：漸進負載區間由它推導 ---
    m_lure = re.search(r'\|\s*ルアー重量[^|]*\|\s*([^|]+)\|', clean_content)
    lure_rating = re.sub(r'\s+', ' ', m_lure.group(1).strip().replace('（', ' (').replace('）', ')')) if m_lure else None
    max_lure = parse_lure_max_g(lure_rating)
    if not lure_rating:
        missing.append("ルアー重量")
    elif max_lure is None:
        missing.append("ルアー重量（解析不出上限 g）")

    if missing:
        raise ReportParseError(file_name, missing)

    # ---- 以下為選填欄位：解析不到一律 None，圖上顯示「報告未提供」 ----

    m_line = re.search(r'\|\s*適合ライン[^|]*\|\s*([^|]+)\|', clean_content)
    line_rating = re.sub(r'\s+', ' ', m_line.group(1).strip().replace('（', ' (').replace('）', ')')) if m_line else None

    m_weight = re.search(r'\|\s*標準自重\s*\|\s*([\d\.]+)\s*g', clean_content)
    weight_g = float(m_weight.group(1)) if m_weight else None

    m_closed = re.search(r'\|\s*仕舞寸法\s*\|\s*([\d\.]+)\s*cm', clean_content)
    closed_cm = float(m_closed.group(1)) if m_closed else None

    # 種類只從官方六欄的「種類」列取。
    # 🔴 不得從型號後綴反推（原本寫死 ["B","RB","FB","HRB",...]）——那是 DAIWA
    #    專屬的命名知識，屬 references/daiwa_model_naming.md，換廠牌會無聲算錯。
    category = None
    m_cat = re.search(r'\|\s*種類\s*\|\s*([A-Za-z]+)\s*\|\s*([^|]+)\|', clean_content)
    if m_cat:
        code, desc = m_cat.group(1).strip().upper(), m_cat.group(2)
        if code == "B" or any(k in desc for k in ("Baitcasting", "ベイト", "兩軸", "槍柄")):
            category = "Baitcasting"
        elif code == "S" or any(k in desc for k in ("Spinning", "スピニング", "紡車")):
            category = "Spinning"

    # 原廠標的調性：官方 key 有四碼 S／R／F／X，四碼都要留原樣。
    # 🔴 原本寫成「含 F 就是 F，其餘一律 R」——X 與 S 會被吃掉，連根本沒有
    #    調性欄位的報告都會被填上 R，等於憑空捏造一個原廠標示。
    m_taper = re.search(r'\|\s*調性\s*\|\s*([SRFX](?:\s*[／/]\s*[SRFX])?)\s*[^|]*\|', clean_content)
    official_taper = re.sub(r'\s+', '', m_taper.group(1)) if m_taper else None

    m_calc_act = re.search(r'物理結構判定[：:]\s*([^\n]+)', clean_content)
    geom_action = m_calc_act.group(1).strip() if m_calc_act else None

    butt_excess = parse_butt_excess(clean_content)

    # 竿先結構只認通用詞彙（Output Style §2 規定報告要寫成
    # 「ソリッドティップ（solid tip）」「チューブラー（tubular）」）。
    # 🔴 不得改認廠牌技術名稱或型號後綴（原本是 "MEGA TOP" 與 "-ST"）。
    if re.search(r'ソリッド|solid\s*tip', raw_content, re.IGNORECASE):
        tip_struct = "Solid Tip"
    elif re.search(r'チューブラー|tubular', raw_content, re.IGNORECASE):
        tip_struct = "Tubular"
    else:
        tip_struct = None

    taper_ratio, ratio_source = parse_taper_ratio(clean_content, tip_dia_mm, butt_dia_mm)

    taper_letter = official_taper[0] if official_taper else None
    if tip_struct == "Solid Tip":
        initial_flex = SOLID_TIP_FLEX_POINT
    else:
        initial_flex = FLEX_POINT_BY_TAPER.get(taper_letter, FLEX_POINT_UNKNOWN)

    power_stiffness = 1.2 if max_lure <= 5 else (1.6 if max_lure <= 10 else (2.0 if max_lure <= 18 else 3.0))

    return {
        "model_name": model_name,
        "category": category,
        "basic_specifications": {
            "Length": "{:.2f} m".format(length_m),
            "Tip_Diameter_mm": tip_dia_mm,
            "Butt_Diameter_mm": butt_dia_mm,
            "Taper_Ratio": taper_ratio,
            "Taper_Ratio_Source": ratio_source,
            "Lure_Rating": lure_rating,
            "Line_Rating": line_rating,
            "Weight_g": weight_g,
            "Closed_Length_cm": closed_cm,
        },
        "taper_action_analysis": {
            "Official_Taper_Code": official_taper,
            "Geometry_Calculated_Action": geom_action,
            "Butt_Excess_Index": butt_excess,
        },
        # 🔴 材質與技術一律留 None。原本這裡寫死 "HVF NANOPLUS" 與 "X45"，
        #    每一支竿都被蓋上同一組技術，還會印進 engineering 圖的規格方塊，
        #    等於每張圖都在宣稱一個沒查證過的事實。報告裡沒有可靠的結構化技術
        #    欄位可解析，所以誠實留空，圖上顯示「報告未提供」。
        "material_and_structure_effects": {
            "Tip_Structure": tip_struct,
            "Blank_Material": None,
            "Anti_Twist_Tech": None,
        },
        "curve_plotting_parameters": {
            "initial_flex_point_pct": initial_flex,
            "power_stiffness_factor": power_stiffness,
            "load_transition_shift_rate": 0.35,
            "tip_flexibility_multiplier": 1.0,
            "butt_stiffness_multiplier": 1.0,
        },
    }


def do_extract(input_dir, output_file):
    md_files = sorted(glob.glob(os.path.join(input_dir, "*_分析報告.md")))
    if not md_files:
        print(f"[ERROR] No *_分析報告.md files found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    # 🔴 單一檔案缺資料時不得中斷整批：原本在 parse 裡直接 sys.exit(1)，
    #    第 3 份壞掉就會把前 2 份已解析的成果一起丟掉。
    #    改為逐檔收集錯誤，成功的照常寫入 JSON，最後一次列出所有缺漏；
    #    但只要有任何一份失敗就以非 0 結束——SKILL.md 規定 AI 必須停下來問
    #    使用者，不得自行補值繼續。
    dataset, failures = [], []
    for fp in md_files:
        try:
            dataset.append(parse_report_file(fp))
            print(f"  [+] Parsed: {os.path.basename(fp)}")
        except ReportParseError as err:
            failures.append(err)
            print(f"  [!] Skipped: {err.file_name}（缺 {'、'.join(err.missing)}）", file=sys.stderr)

    if dataset:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)
        print(f"[SUCCESS] {len(dataset)} / {len(md_files)} 份報告已寫入 {output_file}")

    if failures:
        print("", file=sys.stderr)
        print(f"[ERROR] {len(failures)} 份報告缺少繪圖必需欄位，未納入 JSON：", file=sys.stderr)
        for err in failures:
            print(f"    ・{err.file_name} → 缺 {'、'.join(err.missing)}", file=sys.stderr)
        print("    → 請在報告裡補齊這些欄位後重跑 extract。", file=sys.stderr)
        print("    🔴 不得自行填入推測值，也不得改本腳本繞過檢查。", file=sys.stderr)
        sys.exit(1)

# ==========================================
# COMMON PHYSICS & PLOTTING UTILS
# ==========================================
def parse_length_cm(length_str):
    """'2.18 m' → 218.0。

    🔴 解析不到就報錯，不回傳預設值。原本這裡在失敗時默默回傳 210.0，
       全長是曲線的基礎尺度，猜一個等於整張圖都是假的。
    """
    m = re.search(r'([\d\.]+)', str(length_str or ""))
    if not m:
        raise ValueError("無法解析全長：{!r}。請重跑 extract，不要手動補值。".format(length_str))
    return float(m.group(1)) * 100.0

def require_spec(specs, key):
    """取繪圖必需的數值欄位。缺值直接報錯——不得用預設值撐過去。"""
    value = specs.get(key)
    if value is None:
        raise ValueError("JSON 缺少必需欄位 {}；請重跑 extract，不要手動補值。".format(key))
    return float(value)

def show_or_missing(value, suffix=""):
    """圖上顯示用：None／空字串一律顯示「報告未提供」，不得填 N/A 以外的猜測值。"""
    if value is None or value == "":
        return "報告未提供"
    return "{}{}".format(sanitize_text(value) if isinstance(value, str) else value, suffix)

def sanitize_text(text):
    if not isinstance(text, str): return str(text)
    for old, new in [("〜", " - "), ("~", " - "), ("【", "["), ("】", "]"), ("•", "-"), ("号", "No."), ("號", "No."), ("✅", ""), ("※", "*")]:
        text = text.replace(old, new)
    return text.strip()

def get_rod_color(idx, total):
    return ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'][idx % 10]

# ==========================================
# ZENAQ STYLE PHYSICS & PLOTS
# ==========================================
def calculate_bending_curve_45deg(rod_data, load_g, num_points=300):
    specs = rod_data["basic_specifications"]
    params = rod_data["curve_plotting_parameters"]
    length_cm = parse_length_cm(specs.get("Length"))
    tip_dia, butt_dia = require_spec(specs, "Tip_Diameter_mm"), require_spec(specs, "Butt_Diameter_mm")
    p_flex0 = require_spec(params, "initial_flex_point_pct") / 100.0
    k_power = require_spec(params, "power_stiffness_factor")
    
    ds = length_cm / (num_points - 1)
    s_norm = np.linspace(0.0, 1.0, num_points)
    taper_power = 1.0 + max(0.0, (0.5 - p_flex0) * 4.0)
    dia_profile = tip_dia + (butt_dia - tip_dia) * ((1.0 - s_norm) ** taper_power)
    compliance = (1.0 / (dia_profile ** 3.0)) / k_power

    force_mag = 0.0003 * load_g
    theta = np.full(num_points, 3.0 * math.pi / 4.0)
    X, Y = np.zeros(num_points), np.zeros(num_points)

    for _ in range(60):
        dX, dY = ds * np.cos(theta), ds * np.sin(theta)
        X, Y = np.cumsum(dX) - dX[0], np.cumsum(dY) - dY[0]
        moment = force_mag * np.maximum(0.0, X - X[-1])
        dTheta = moment * compliance * ds
        theta_target = 3.0 * math.pi / 4.0 + np.cumsum(dTheta) - dTheta[0]
        theta = 0.1 * theta_target + 0.9 * theta
    return X, Y

def get_dynamic_load_list(lure_str):
    # 與 parse_lure_max_g 共用同一套解析，避免兩處規則各自漂移
    # （原本這裡與 parser 各寫一份，parser 那份還會抓到區間下限）。
    max_lure = parse_lure_max_g(lure_str)
    if max_lure is None:
        raise ValueError("無法從 {!r} 解析路亞負載上限；請重跑 extract。".format(lure_str))

    extreme_weight = 500 if max_lure > 40 else (250 if max_lure > 15 else 100)
    loads = [round(max_lure * x, 1) for x in [0.2, 0.5, 1.0, 1.5, 2.0]]
    loads = sorted(list(set([l for l in loads if l < extreme_weight] + [extreme_weight])))
    return [int(x) if x == int(x) else x for x in loads]

def plot_zenaq_comparison(rod_list, category_name, load_g, output_dir):
    fig, ax = plt.subplots(figsize=(12, 8), dpi=300)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#dddddd')
    ax.spines['left'].set_color('#dddddd')
    ax.grid(True, linestyle="-", alpha=0.3, color="#bbbbbb")

    hx, hy = np.linspace(0, 35.0 * math.cos(3*math.pi/4), 10), np.linspace(0, 35.0 * math.sin(3*math.pi/4), 10)
    ax.plot(hx, hy, color="#222222", linewidth=6, zorder=5, solid_capstyle='round')

    min_x, max_y = 0, 0
    for idx, rod in enumerate(rod_list):
        model_name, color = rod["model_name"], get_rod_color(idx, len(rod_list))
        X, Y = calculate_bending_curve_45deg(rod, load_g)
        ax.plot(X, Y, label=model_name, color=color, linewidth=2.0, zorder=4)
        min_x, max_y = min(min_x, np.min(X)), max(max_y, np.max(Y))

    # Apply dedicated margins: Top 15% for title, Right 25% for info/legend
    plt.subplots_adjust(left=0.05, right=0.75, top=0.85, bottom=0.05)

    # Global Title at the very top
    # 🔴 標題不得寫死廠牌或系列名（原本是 "HEARTLAND ..."）——
    #    本腳本不知道進來的是哪個系列，寫死等於在圖上宣告一個沒查證的事實。
    fig.suptitle(f"{category_name} COMPARISON", fontsize=24, color="#333333", fontweight='bold')

    # Load Box in the right margin
    props = dict(boxstyle="square,pad=0.5", facecolor="black", edgecolor="black")
    fig.text(0.87, 0.85, f"Load\n{load_g}\ngram", fontsize=16, color="white", fontweight='bold', ha='center', va='top', bbox=props)

    ax.set_xlim(min_x * 1.1, 10)
    ax.set_ylim(-10, max_y * 1.1)
    ax.set_aspect('equal', adjustable='box')
    ax.set_xticks([])
    ax.set_yticks([])
    
    # Legend safely anchored outside the plot area
    ax.legend(loc="lower left", bbox_to_anchor=(1.05, 0.0), frameon=False, fontsize=12)

    out_path = os.path.join(output_dir, f"{category_name}_Comparison_{load_g}g.png")
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"[SUCCESS] Created {out_path}")

def plot_zenaq_progressive(rod, load_list, output_dir):
    model_name = rod["model_name"]
    fig, ax = plt.subplots(figsize=(10, 8), dpi=300)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#dddddd')
    ax.spines['left'].set_color('#dddddd')
    ax.grid(True, linestyle="-", alpha=0.3, color="#bbbbbb")

    hx, hy = np.linspace(0, 35.0 * math.cos(3*math.pi/4), 10), np.linspace(0, 35.0 * math.sin(3*math.pi/4), 10)
    ax.plot(hx, hy, color="#222222", linewidth=6, zorder=5, solid_capstyle='round')

    cmap = plt.get_cmap("rainbow")
    min_x, max_y = 0, 0
    for i, load_g in enumerate(load_list):
        color = cmap(i / max(1, len(load_list)-1))
        X, Y = calculate_bending_curve_45deg(rod, load_g)
        ax.plot(X, Y, label=f"{load_g}g", color=color, linewidth=2.0, zorder=4)
        ax.scatter([X[-1]], [Y[-1]], color=color, s=20, zorder=5)
        min_x, max_y = min(min_x, np.min(X)), max(max_y, np.max(Y))

    # Apply dedicated margins: Top 15% for title, Right 25% for info/legend
    plt.subplots_adjust(left=0.05, right=0.75, top=0.85, bottom=0.05)

    # Global Title
    fig.suptitle("PROGRESSIVE LOAD CURVES", fontsize=24, color="#333333", fontweight='bold')

    # Model Box in right margin
    props = dict(boxstyle="square,pad=0.5", facecolor="black", edgecolor="black")
    fig.text(0.87, 0.85, f"MODEL\n{model_name}", fontsize=14, color="white", fontweight='bold', ha='center', va='top', bbox=props)
    
    # Specs in right margin
    taper = rod["taper_action_analysis"].get("Geometry_Calculated_Action")
    if taper:
        fig.text(0.87, 0.70, sanitize_text(taper), fontsize=12, color="#555555", ha='center', va='center')

    lure_str = rod.get("basic_specifications", {}).get("Lure_Rating")
    if lure_str: fig.text(0.87, 0.65, f"Lure: {sanitize_text(lure_str)}", fontsize=12, color="#555555", ha='center', va='center')

    ax.set_xlim(min_x * 1.1, 10)
    ax.set_ylim(-10, max_y * 1.1)
    ax.set_aspect('equal', adjustable='box')
    ax.set_xticks([])
    ax.set_yticks([])
    
    # Legend safely anchored outside
    ax.legend(loc="lower left", bbox_to_anchor=(1.05, 0.0), frameon=False, fontsize=12, title="Load (g)", title_fontsize=12)

    out_path = os.path.join(output_dir, "Progressive_Curves", f"{model_name}_Progressive.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"[SUCCESS] Created {out_path}")

def do_plot_zenaq(json_file, output_dir):
    if not os.path.exists(json_file):
        print(f"[ERROR] Data file not found: {json_file}", file=sys.stderr)
        sys.exit(1)

    with open(json_file, "r", encoding="utf-8") as f:
        rod_dataset = json.load(f)

    baitcasting_rods = [r for r in rod_dataset if r.get("category") == "Baitcasting"]
    spinning_rods = [r for r in rod_dataset if r.get("category") == "Spinning"]

    # 種類解析不到的竿不再默默歸類為 Spinning——那會讓它跟一群紡車竿同框比較。
    # 改為明確點名，並排除在對比圖之外（單竿的漸進圖仍照常產生）。
    uncategorized = [r["model_name"] for r in rod_dataset if not r.get("category")]
    if uncategorized:
        print("[WARN] 以下釣竿的報告裡沒有解析到「種類」欄位，已排除於對比圖之外："
              + "、".join(uncategorized), file=sys.stderr)

    os.makedirs(output_dir, exist_ok=True)

    for rods, name in ((baitcasting_rods, "BAITCASTING"), (spinning_rods, "SPINNING")):
        if not rods:
            print(f"[WARN] 沒有 {name} 類型的釣竿，略過該對比圖。", file=sys.stderr)
            continue
        for load_g in (28, 100):
            plot_zenaq_comparison(rods, name, load_g, output_dir)

    for rod in rod_dataset:
        lure_str = rod.get("basic_specifications", {}).get("Lure_Rating")
        plot_zenaq_progressive(rod, get_dynamic_load_list(lure_str), output_dir)

    print("[SUCCESS] All ZENAQ-style plots generated successfully!")

# ==========================================
# ENGINEERING STYLE PHYSICS & PLOTS
# ==========================================
def calculate_bending_curve_horizontal(rod_data, load_g, num_points=300):
    specs = rod_data["basic_specifications"]
    params = rod_data["curve_plotting_parameters"]
    length_cm = parse_length_cm(specs.get("Length"))
    tip_dia, butt_dia = require_spec(specs, "Tip_Diameter_mm"), require_spec(specs, "Butt_Diameter_mm")
    p_flex0 = require_spec(params, "initial_flex_point_pct") / 100.0
    k_power = require_spec(params, "power_stiffness_factor")
    
    ds = length_cm / (num_points - 1)
    s_norm = np.linspace(0.0, 1.0, num_points)
    taper_power = 1.0 + max(0.0, (0.5 - p_flex0) * 4.0)
    dia_profile = tip_dia + (butt_dia - tip_dia) * ((1.0 - s_norm) ** taper_power)
    compliance = (1.0 / (dia_profile ** 3.0)) / k_power

    # Adjusted force for horizontal geometry to get realistic deflections
    force_mag = 0.00015 * load_g
    theta = np.full(num_points, 0.0) # Horizontal start
    X, Y = np.zeros(num_points), np.zeros(num_points)

    for _ in range(60):
        dX, dY = ds * np.cos(theta), ds * np.sin(theta)
        X, Y = np.cumsum(dX) - dX[0], np.cumsum(dY) - dY[0]
        # Moment arm: distance from tip
        moment = force_mag * np.maximum(0.0, X[-1] - X)
        # Bending downwards: negative curvature
        dTheta = -moment * compliance * ds
        theta_target = 0.0 + np.cumsum(dTheta) - dTheta[0]
        theta = 0.1 * theta_target + 0.9 * theta
    return X, Y

def plot_engineering_chart(rod_data, output_dir):
    model_name = sanitize_text(rod_data["model_name"])
    category = rod_data.get("category")
    category_suffix = " ({})".format(sanitize_text(category)) if category else ""
    specs = rod_data["basic_specifications"]
    taper_info = rod_data["taper_action_analysis"]
    mat_info = rod_data["material_and_structure_effects"]
    params = rod_data["curve_plotting_parameters"]

    length_cm = parse_length_cm(specs.get("Length"))
    # 🔴 缺值一律顯示「報告未提供」。原本 Tip 缺值會默默顯示成 "Tubular"，
    #    調性缺值會顯示成 parser 憑空填的 "R"——兩者都是在圖上說謊。
    official_taper = show_or_missing(taper_info.get("Official_Taper_Code"))
    calc_action = show_or_missing(taper_info.get("Geometry_Calculated_Action"))
    tip_struct = show_or_missing(mat_info.get("Tip_Structure"))

    loads = [
        (100, "Light Load (100g)", "#1f77b4", "-", 2.0),
        (250, "Medium Load (250g)", "#2ca02c", "--", 2.2),
        (500, "Heavy Load (500g)", "#ff7f0e", "-.", 2.4),
        (1000, "Max Load (1000g)", "#d62728", "-", 2.8),
    ]

    fig, ax = plt.subplots(figsize=(11, 7), dpi=300)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fcfcfc")

    handle_len = min(35.0, length_cm * 0.16)
    ax.axvspan(-2, handle_len, color="#e0e0e0", alpha=0.4, zorder=1, label="Grip / Reel Seat Zone")
    ax.plot([0, handle_len], [0, 0], color="#555555", linewidth=5, zorder=2)
    ax.plot([0, length_cm], [0, 0], color="#888888", linestyle=":", linewidth=1.5, label="Unloaded Rod Baseline", zorder=3)

    min_y = 0.0
    for load_g, label_text, color_code, line_style, line_width in loads:
        X, Y = calculate_bending_curve_horizontal(rod_data, load_g)
        ax.plot(X, Y, label=label_text, color=color_code, linestyle=line_style, linewidth=line_width, zorder=4)
        ax.scatter(X[-1], Y[-1], color=color_code, s=40, zorder=5)
        min_y = min(min_y, float(np.min(Y)))

    ax.set_xlabel("Horizontal Position from Butt (cm)", fontsize=11, fontweight="bold", labelpad=8)
    ax.set_ylabel("Vertical Deflection (cm)", fontsize=11, fontweight="bold", labelpad=8)
    
    # 🔴 同上：不得寫死 "DAIWA Heartland"。型號字串本身就足以識別這支竿。
    title_str = f"{model_name}{category_suffix} - Load Bending Curves"
    subtitle_str = f"Official Taper: {official_taper} | Tip: {tip_struct} | Calc Action: {calc_action}"
    ax.set_title(f"{title_str}\n{subtitle_str}", fontsize=12, fontweight="bold", pad=12)

    ax.grid(True, linestyle="--", alpha=0.5, color="#bbbbbb")
    ax.set_xlim(-5, length_cm + 10)
    ax.set_ylim(min_y * 1.18, max(10, -min_y * 0.15))

    ratio_source = specs.get("Taper_Ratio_Source")
    ratio_note = "（{}）".format(ratio_source) if ratio_source else ""
    info_lines = [
        "[Specifications]",
        "- Length: {}".format(show_or_missing(specs.get("Length"))),
        "- Weight: {} | Closed: {}".format(
            show_or_missing(specs.get("Weight_g"), "g"),
            show_or_missing(specs.get("Closed_Length_cm"), "cm")),
        "- Tip/Butt Dia: {}mm / {}mm".format(specs.get("Tip_Diameter_mm"), specs.get("Butt_Diameter_mm")),
        "- Taper Ratio: {}{} | Butt Excess: {}".format(
            specs.get("Taper_Ratio"), ratio_note,
            show_or_missing(taper_info.get("Butt_Excess_Index"))),
        "- Lure: {}".format(show_or_missing(specs.get("Lure_Rating"))),
        "- Line: {}".format(show_or_missing(specs.get("Line_Rating"))),
        "",
        # 🟡 這一區塊是本腳本的繪圖參數，不是原廠數據——標題就要講明，
        #    否則看圖的人會把它當成規格表的一部分。
        "[Model Parameters] 繪圖用推估值，非原廠數據",
        "- Initial Flex Point: {}%".format(params.get("initial_flex_point_pct")),
        "- Power Stiffness (Kp): {}".format(params.get("power_stiffness_factor")),
        "- Load Shift Rate (eta): {}".format(params.get("load_transition_shift_rate")),
        "- Tip Mult: {} | Butt Mult: {}".format(
            params.get("tip_flexibility_multiplier"), params.get("butt_stiffness_multiplier")),
    ]

    # 🔴 技術欄位只在報告真的有提供時才印。原本無條件印出寫死的
    #    "HVF NANOPLUS" / "X45" / "Butt Structure: None (3DX Excluded)"，
    #    等於每張圖都在宣稱三個沒查證過的事實。
    tech_fields = [
        ("Material", mat_info.get("Blank_Material")),
        ("Tip Structure", mat_info.get("Tip_Structure")),
        ("Anti-Twist", mat_info.get("Anti_Twist_Tech")),
    ]
    known_tech = [(label, value) for label, value in tech_fields if value]
    if known_tech:
        info_lines.append("")
        info_lines.append("[Tech Features] 僅列報告已載明者")
        info_lines.extend("- {}: {}".format(label, sanitize_text(value)) for label, value in known_tech)

    info_text = "\n".join(info_lines)

    props = dict(boxstyle="round,pad=0.6", facecolor="#ffffff", edgecolor="#cccccc", alpha=0.92)
    ax.text(0.02, 0.04, info_text, transform=ax.transAxes, fontsize=8.5, verticalalignment="bottom", bbox=props, zorder=6, family="sans-serif")

    ax.legend(loc="upper right", frameon=True, facecolor="#ffffff", framealpha=0.9, fontsize=9.5)

    out_path = os.path.join(output_dir, "Engineering_Curves", f"{model_name}_Engineering.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"[SUCCESS] Generated engineering bending curve plot: {out_path}")

def do_plot_engineering(json_file, output_dir):
    if not os.path.exists(json_file):
        print(f"[ERROR] Data file not found: {json_file}", file=sys.stderr)
        sys.exit(1)

    with open(json_file, "r", encoding="utf-8") as f:
        rod_dataset = json.load(f)

    os.makedirs(os.path.join(output_dir, "Engineering_Curves"), exist_ok=True)
    
    for rod in rod_dataset:
        plot_engineering_chart(rod, output_dir)

    print("[SUCCESS] All Engineering-style plots generated successfully!")


# ==========================================
# CLI ENTRY POINT
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Rod Curve Generator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_extract = subparsers.add_parser("extract", help="Parse markdown files to JSON")
    parser_extract.add_argument("--input-dir", required=True, help="Directory containing *_分析報告.md files")
    parser_extract.add_argument("--output", required=True, help="Output JSON file path")

    parser_plot_zenaq = subparsers.add_parser("plot-zenaq", help="Plot ZENAQ-style bending curves from JSON")
    parser_plot_zenaq.add_argument("--input", required=True, help="Input JSON file path")
    parser_plot_zenaq.add_argument("--output-dir", required=True, help="Directory to save PNG plots")

    parser_plot_eng = subparsers.add_parser("plot-engineering", help="Plot Engineering-style bending curves from JSON")
    parser_plot_eng.add_argument("--input", required=True, help="Input JSON file path")
    parser_plot_eng.add_argument("--output-dir", required=True, help="Directory to save PNG plots")

    args = parser.parse_args()

    if args.command == "extract":
        do_extract(args.input_dir, args.output)
    elif args.command == "plot-zenaq":
        do_plot_zenaq(args.input, args.output_dir)
    elif args.command == "plot-engineering":
        do_plot_engineering(args.input, args.output_dir)

if __name__ == "__main__":
    main()
