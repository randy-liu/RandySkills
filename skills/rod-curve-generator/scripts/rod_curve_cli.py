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


def parse_lure_range_g(lure_str):
    """取路亞負載的下限與上限（g），回傳 (min, max)。取不到的那一端為 None。"""
    if not lure_str:
        return (None, None)
    m = re.search(r'([\d\.]+)\s*[〜～~\-–—]+\s*([\d\.]+)\s*g', lure_str)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (min(lo, hi), max(lo, hi))
    g_matches = [float(x) for x in re.findall(r'([\d\.]+)\s*g', lure_str)]
    if len(g_matches) > 1:
        return (min(g_matches), max(g_matches))
    if g_matches:
        return (None, g_matches[0])
    return (None, None)


def parse_lure_max_g(lure_str):
    """取路亞負載上限（g）。取不到一律回傳 None，不給預設值。"""
    return parse_lure_range_g(lure_str)[1]


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


def parse_tech_table(raw_content):
    """讀報告 §1-2「搭載技術」表，回傳 {技術名稱: 是否搭載}。

    這是技術欄位【唯一】的證據來源——表格是報告逐竿判定的結果，
    ✅／❌ 都由該竿的官方 ※ 標註或介紹文推導而來。
    """
    section = re.search(r'###\s*1-2[^\n]*\n(.*?)(?=###\s*1-3|##\s*2|\Z)',
                        raw_content, re.DOTALL)
    text = section.group(1) if section else raw_content

    table = re.search(r'((?:\|[^\n]+\n?)+)', text)
    if not table:
        return {}

    status = {}
    for line in table.group(1).strip().split("\n"):
        cols = [clean_markdown_tags(c) for c in line.split("|")[1:-1]]
        if len(cols) < 2:
            continue
        name, state = cols[0].strip(), cols[1].strip()
        if not name or name == "技術" or name.startswith("---"):
            continue
        status[name] = ("✅" in state) and ("非搭載" not in state)
    return status


def parse_materials(raw_content, tip_dia_mm, model_name):
    """由技術表推導材質與結構欄位。

    🔴 查不到就留 None，不得假設。原始的 extract_rod_data.py 在查不到時
       會落到 `blank_material = "HVF NANOPLUS"`、`anti_twist = "X45 Full Shield"`，
       並把 `blank_construction` 寫死成 "TUBULAR POWER SLIM"。Heartland 全系列
       剛好都有這些技術所以看不出問題，但那是「猜系列的共通值」——換系列或
       換廠牌就會在圖上宣稱一個沒查證過的技術。
    """
    tech = parse_tech_table(raw_content)

    def mounted(*names):
        return any(tech.get(n) for n in names)

    if mounted("SVF COMPILE-X", "SVF"):
        blank_material = "SVF COMPILE-X"
    elif mounted("HVF NANOPLUS", "HVF ナノプラス"):
        blank_material = "HVF NANOPLUS"
    else:
        blank_material = None

    if mounted("X45フルシールド", "X45 フルシールド"):
        anti_twist = "X45 Full Shield"
    elif mounted("X45"):
        anti_twist = "X45"
    else:
        anti_twist = None

    if mounted("3DX"):
        butt_structure = "3DX (Butt Only)" if re.search(r'只(在|施加在)元段', raw_content) else "3DX"
    elif "3DX" in tech:  # 表裡有這一列但標 ❌ ＝ 已查證為未搭載
        butt_structure = "None (3DX Excluded)"
    else:
        butt_structure = None

    tip_struct = parse_tip_structure(raw_content)
    if tip_struct == "Solid Tip":
        label = "MEGATOP " if mounted("MEGA TOP", "メガトップ") else ""
        tip_struct = "Solid Tip ({}{:.1f}mm)".format(label, tip_dia_mm)

    return {
        "Blank_Material": blank_material,
        "Tip_Structure": tip_struct,
        "Blank_Construction": "TUBULAR POWER SLIM" if mounted("TUBULAR POWER SLIM") else None,
        "Anti_Twist_Tech": anti_twist,
        "Butt_Structure": butt_structure,
        "Joint_Tech": ("V-JOINT + へら合わせ" if mounted("へら合わせ")
                       else ("V-JOINT" if mounted("V-JOINT") else None)),
        # 表裡有這一列但標 ❌ ＝ 已查證為未搭載，是結論不是資料缺口，
        # 所以寫出否定值而不是 None（與 Butt_Structure 的處理一致）。
        "Reel_Seat_Tech": ("AIR SENSOR SEAT" if mounted("AIR SENSOR SEAT")
                           else ("Non-Air Sensor Seat" if "AIR SENSOR SEAT" in tech else None)),
    }


# 元端行為的門檻。🔴 必須與 rod-spec-decrypter 的 calculate_taper.py 一致
# （`SLIM_BUTT_FLAG = 8.5`、`BUTT_OVERCAP_FLAG = 100.0`）——報告引述的就是那兩條
# 警示，圖上畫的若是另一套判定，同一支竿就會有兩種互相矛盾的說法。
SLIM_BUTT_DIA_MM = 8.5
BUTT_OVERCAP_INDEX = 100.0

# 分類對柔度剖面「對比度」的指數。以「後半段吃掉多少比例的彎曲」為校準目標。
# 🔴 不能用單純的乘數：竿尖與元端的柔度差距來自 1/d³，702UL+FS-ST23 是 1180 倍，
#    在後半段乘上 2〜3 倍完全壓不過去（實測只把後段參與從 13% 拉到 17%）。
#    改為調整整條剖面的對比度：指數 < 1 把落差壓平（整支一起彎），
#    > 1 把落差放大（彎曲更集中前端）。
#    校準依據：以「後半段吃掉多少比例的彎曲」為指標，slim 竿要接近均勻（約 50%
#    ＝整支一起彎），overcapacity 竿要明確墊底。0.72 讓 702UL+FS-ST23 在兩支
#    解算器都落在 47%；1.25 讓 722LRS-21 降到 6%，低於所有無警示的竿。
BUTT_CONTRAST_GAMMA = {"slim": 0.72, "overcapacity": 1.25, "normal": 1.0}


def classify_butt_behaviour(butt_dia_mm, butt_excess):
    """元端在受力時的行為：'slim'／'overcapacity'／'normal'。

    報告的兩個關鍵判定都是**絕對尺度**的，而兩支解算器的柔度剖面都只看**相對**
    錐度（竿尖比屁股細多少），結構上表達不出來：

      ・元徑 < 8.5mm  → 全體纖細 → 中後段缺乏絕對剛度 →「整支一起彎」
      ・元端過剩 ≥ 100 → 元端在設計負載內不會被撓曲 →「元端不參與作動」

    先前 702UL+FS-ST23（全體纖細）與 722LRS-21（元端過剩）這兩支診斷**相反**的竿，
    在 45 度圖上被畫成一模一樣的後半段參與度（都是 13%）。

    ⚠️ 兩個條件可能同時成立，此時 **slim 優先**：絕對剛度不足是更強的物理事實，
       而元端過剩指數的分母含負載上限，輕竿的上限本來就小，容易假性偏高。
    """
    if butt_dia_mm is not None and butt_dia_mm < SLIM_BUTT_DIA_MM:
        return "slim"
    if butt_excess is not None and butt_excess >= BUTT_OVERCAP_INDEX:
        return "overcapacity"
    return "normal"


def apply_butt_behaviour(compliance, behaviour):
    """依元端行為分類調整柔度剖面的對比度。

    以**竿尖的柔度為錨點**（保持不變），只壓縮或放大其餘部位相對於竿尖的落差：

      ・slim         → 指數 < 1，元端柔度被拉近竿尖 → 整支一起彎
      ・overcapacity → 指數 > 1，元端柔度被推得更低 → 元端幾乎不動

    錨在竿尖是為了不改變「這支竿整體彎多少」，只改變「彎在哪裡」。
    """
    gamma = BUTT_CONTRAST_GAMMA.get(behaviour, 1.0)
    if gamma == 1.0:
        return compliance
    ref = float(np.max(compliance))
    if ref <= 0:
        return compliance
    return ref * (compliance / ref) ** gamma


def derive_curve_parameters(tip_struct, butt_struct, taper_code, tip_dia_mm, butt_dia_mm,
                            taper_ratio, butt_excess, max_lure):
    """由幾何與調性推導繪圖參數。

    🟡 這些門檻是人看著圖調出來的經驗值，不是原廠數據——圖上已標明
       「繪圖用推估值」。規則搬自 extract_rod_data.py，但拿掉了原本
       `elif tip_dia_mm == 1.6 and taper_ratio == 6.50:` 那一條：用兩個浮點數
       精確比對，實際上是在指定某一支特定的竿，只是包裝成規則。
    """
    is_solid = "Solid Tip" in (tip_struct or "")
    is_stiffened = (tip_struct or "") == "Tubular (Stiffened Tip)"
    excess = butt_excess or 0.0

    if is_solid:
        flex_point = 22.0 if tip_dia_mm <= 0.8 else (25.0 if tip_dia_mm <= 1.2 else 28.0)
    elif taper_code == "F":
        flex_point = 30.0 if tip_dia_mm <= 1.4 else 35.0
    elif is_stiffened:
        flex_point = 42.0
    elif taper_ratio >= 7.0:
        flex_point = 44.0
    elif tip_dia_mm >= 2.0:
        flex_point = 46.0
    elif taper_ratio <= 6.0:
        flex_point = 48.0
    else:
        flex_point = 45.0

    if max_lure <= 5.0:
        k_power = 1.1 if is_solid else 1.2
    elif max_lure <= 7.0:
        k_power = 1.5
    elif max_lure <= 10.0:
        k_power = 1.6
    elif max_lure <= 11.0:
        k_power = 1.25
    elif max_lure <= 14.0:
        k_power = 1.75
    elif max_lure <= 18.0:
        k_power = 2.0
    elif max_lure <= 21.0:
        k_power = 2.5
    elif max_lure >= 28.0:
        k_power = 3.0
    else:
        k_power = 2.0

    has_3dx = "3DX" in (butt_struct or "") and "Excluded" not in (butt_struct or "")

    if is_solid:
        eta = 0.45 if tip_dia_mm <= 0.8 else 0.25
    elif excess >= 100.0:
        eta = 0.25
    elif is_stiffened:
        eta = 0.40
    elif taper_ratio <= 6.0:
        eta = 0.45
    elif has_3dx and taper_code == "R":
        eta = 0.42 if max_lure >= 21.0 else 0.38
    else:
        eta = 0.35

    if is_solid:
        mu_tip = 1.35 if tip_dia_mm <= 0.8 else 1.30
    elif is_stiffened:
        mu_tip = 0.90
    elif max_lure >= 21.0:
        mu_tip = 0.95
    else:
        mu_tip = 1.0

    if butt_dia_mm <= 8.0:
        mu_butt = 0.95
    elif excess >= 100.0:
        mu_butt = 1.40
    elif (butt_struct or "") == "3DX (Butt Only)" and max_lure >= 28.0:
        mu_butt = 1.30
    elif has_3dx:
        mu_butt = 1.25 if max_lure >= 21.0 else 1.20
    elif is_stiffened:
        mu_butt = 1.10
    elif taper_ratio <= 6.0:
        mu_butt = 1.05
    else:
        mu_butt = 1.15

    return {
        "initial_flex_point_pct": flex_point,
        "power_stiffness_factor": k_power,
        "load_transition_shift_rate": eta,
        "tip_flexibility_multiplier": mu_tip,
        "butt_stiffness_multiplier": mu_butt,
    }


def parse_tip_structure(raw_content):
    """判定竿先是實心還是空心。判不出來回傳 None，不猜。

    🔴 只認 Step 3 的判定句，不做全文關鍵字搜尋。報告裡到處都有「solid tip」
       這個詞——章節標題就叫 Solid Tip Check，空心竿的段落也會寫「型號後綴
       沒有 -ST（Solid Tip）」來說明它**不是**實心。全文搜尋的結果是 12 支竿
       全部被判成實心。

    判定句的格式（兩種都以「本竿為」開頭）：
        本竿為チューブラー（tubular，空心竿先）。
        本竿為 ソリッドティップ（solid tip，實心竿先），且是……
    """
    for m in re.finditer(r'本竿為\s*([^\n。]{0,40})', raw_content):
        verdict = m.group(1)
        if re.search(r'ソリッド|solid\s*tip|實心', verdict, re.IGNORECASE):
            return "Solid Tip"
        if re.search(r'チューブラー|tubular|空心', verdict, re.IGNORECASE):
            return "Tubular"
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
    m_len = re.search(r'\|\s*全長[^|]*\|\s*([\d\.]+)\s*m', clean_content)
    length_m = float(m_len.group(1)) if m_len else None
    if length_m is None:
        missing.append("全長")

    # --- 先径・元径（必需）：錐度剖面 ---
    # 官方欄位名是「先径・元径」（中黑點），報告轉寫時可能改成 ／ 或 /，
    # 繁體報告也可能寫成「先徑」，故字形與分隔符都放寬。
    sep = r'[・･/／]'
    m_dia = re.search(
        r'\|\s*先[径徑]\s*' + sep + r'\s*元[径徑][^|]*\|\s*([\d\.]+)\s*' + sep + r'\s*([\d\.]+)\s*mm',
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

    # 🔴 欄位名後面可能帶中文註解括號（如「仕舞寸法（收納長度）」），
    #    所以一律用 [^|]* 收尾——原本要求欄位名後直接接 |，12 支竿的
    #    仕舞寸法全部抓不到。
    m_weight = re.search(r'\|\s*標準自重[^|]*\|\s*([\d\.]+)\s*g', clean_content)
    weight_g = float(m_weight.group(1)) if m_weight else None

    m_closed = re.search(r'\|\s*仕舞寸法[^|]*\|\s*([\d\.]+)\s*cm', clean_content)
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
    taper_ratio, ratio_source = parse_taper_ratio(clean_content, tip_dia_mm, butt_dia_mm)

    materials = parse_materials(raw_content, tip_dia_mm, model_name)
    curve_params = derive_curve_parameters(
        tip_struct=materials["Tip_Structure"],
        butt_struct=materials["Butt_Structure"],
        taper_code=(official_taper[0] if official_taper else None),
        tip_dia_mm=tip_dia_mm,
        butt_dia_mm=butt_dia_mm,
        taper_ratio=taper_ratio,
        butt_excess=butt_excess,
        max_lure=max_lure,
    )

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
        # 材質與技術一律以報告 §1-2 技術表為準；表裡查不到就留 None，不假設。
        "material_and_structure_effects": materials,
        "curve_plotting_parameters": curve_params,
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
    # 只影響圖上顯示；JSON 一律保留報告原文，原文才是證據。
    for old, new in [("〜", " - "), ("~", " - "), ("【", "["), ("】", "]"), ("•", "-"),
                     ("号", "No."), ("號", "No."), ("✅", ""), ("※", "*"),
                     ("ナイロン", "Nylon "), ("／", " / ")]:
        text = text.replace(old, new)
    return text.strip()

def get_rod_color(idx, total):
    return ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'][idx % 10]

# ==========================================
# ZENAQ STYLE PHYSICS & PLOTS
# ==========================================
START_ANGLE_45 = 3.0 * math.pi / 4.0  # 135 度：竿子上舉 45 度、指向左上

# 力量係數。🟡 這是經驗校準值，不是從材料力學推導出來的：原始腳本的註解寫
# 「0.0003 ensures 21g bends a M power rod by ~20 degrees」。因此**曲線之間的
# 相對關係可信，絕對撓曲量不可信**——不得拿圖上的公分數去對照實測。
FORCE_SCALE_45 = 0.0003

# 搏魚負載（g）。這不是路亞重量，是「真的中魚時竿子被拉成什麼樣」的模擬點。
# 🔴 固定值，不得依竿子強弱分級。原本寫成 >15g 跳 250、>40g 跳 500，
#    結果是同一張圖上不同竿的極端值不一樣，彼此無法比較，而且中量級竿
#    會拿到 12 倍額定的荷重，畫出來是一個沒有意義的圈。
FIGHT_LOAD_G = 100.0

# 跨竿對比圖的負載（g）。
# 🔴 這裡**必須**用絕對克數，不能像單竿圖那樣依額定推演——對比圖的意義
#    就是「同一個重量掛上去，各支竿分別彎成什麼樣」。每支竿用自己的額定
#    倍率就等於各畫各的，疊在一張圖上不能比較。
#    50g ＝ 中量級竿的工作區間上緣、輕竿的明顯超載；100g ＝ 搏魚基準。
COMPARISON_LOADS_G = (50, 100)

# 額定區間內的取樣段數。取樣以**等比**分佈於「路亞負載下限 → 上限」之間，
# 例如 5〜21g 得到 5／6.7／8.9／11.8／15.8／21。
# 🔴 不得改用「上限的固定倍率」（曾經是 0.2×〜2.0×）：那會取樣到額定範圍外
#    （2× 額定 = 42g），而且輕竿與重竿的取樣密度不一致。
LOAD_LADDER_STEPS = 6

# 取樣起點＝額定下限 × 此係數，**略低於下限**。
# 目的是讓圖上看得見「餌比原廠建議還輕」時竿子幾乎不吃力的狀態——
# 那是額定區間下緣的意義所在，從下限正好起跳就看不到這一段。
LOAD_LADDER_START_RATIO = 0.8

# 超額負載＝額定上限 × 此倍率，模擬「略微超出原廠建議負載」時的彎曲。
# 額定上限本身仍是取樣點（那是對齊原廠建議的錨點），超額點是額外追加的。
# 各竿共用同一倍率，跨竿的超載程度才一致。
LOAD_OVERLOAD_RATIO = 1.15

# 沒有標示下限時的假設起點（上限的 1/4）。🟡 這是假設，不是原廠資料。
LOAD_LADDER_FALLBACK_MIN_RATIO = 0.25


def solve_bending_45deg(length_cm, tip_dia, butt_dia, p_flex0, k_power,
                        mu_tip, mu_butt, is_solid_tip, load_g, butt_behaviour="normal",
                        num_points=300, load_steps=40, sweeps=15):
    """45 度持竿的大撓度解算。

    🔴 負載必須分步施加。原本一次把整個負載加上去、從打直的初始形狀迭代 60 次，
       負載大時第一輪的力矩臂是最大值，theta 會一次衝過頭，cos/sin 翻符號之後
       整個系統失控——實測 702UL+FS-ST23（0.7mm 實心竿先）在 100g 會轉 520 度，
       捲成一團，而 75g 時還是正常的 137.8 度，中間沒有任何過渡。
       分步加載讓每一步都從已收斂的鄰近形狀出發，同一條件回到 138.4 度，
       且原本就正常的結果完全不受影響（722MRB-20 在 100g：83.9° → 83.8°）。
    """
    ds = length_cm / (num_points - 1)
    s_norm = np.linspace(0.0, 1.0, num_points)  # 0 = 元端（握把），1 = 竿先

    taper_power = 1.0 + max(0.0, (0.5 - p_flex0) * 4.0)
    dia_profile = tip_dia + (butt_dia - tip_dia) * ((1.0 - s_norm) ** taper_power)
    compliance = (1.0 / (dia_profile ** 3.0)) / k_power

    # 實心竿先：最前端 (s^8) 大幅軟化。tubular 竿不套用。
    if is_solid_tip and mu_tip > 1.0:
        compliance = compliance * (1.0 + (mu_tip * 2.0 - 1.0) * (s_norm ** 8))
    # 元端補強／軟化：靠近握把處 ((1-s)^3)。
    # 🔴 條件是 != 1.0 而不是 > 1.0：原本只認補強方向，mu_butt < 1（元徑極細、
    #    屁股頂不住）會被靜默丟棄——702UL+FS-ST23 的 0.95 從來沒有生效過。
    if mu_butt != 1.0:
        compliance = compliance * (1.0 - (1.0 - 1.0 / mu_butt) * ((1.0 - s_norm) ** 3))

    # 報告的絕對剛度判定（全體纖細／元端過剩）。相對錐度剖面表達不出這兩件事。
    compliance = apply_butt_behaviour(compliance, butt_behaviour)

    theta = np.full(num_points, START_ANGLE_45)
    X = Y = np.zeros(num_points)
    for step in range(1, load_steps + 1):
        force_mag = FORCE_SCALE_45 * load_g * (step / load_steps)
        for _ in range(sweeps):
            dX, dY = ds * np.cos(theta), ds * np.sin(theta)
            X, Y = np.cumsum(dX) - dX[0], np.cumsum(dY) - dY[0]
            moment = force_mag * np.maximum(0.0, X - X[-1])
            dTheta = moment * compliance * ds
            theta_target = START_ANGLE_45 + np.cumsum(dTheta) - dTheta[0]
            theta = 0.1 * theta_target + 0.9 * theta
    return X, Y


def rod_butt_behaviour(rod_data):
    """從 JSON 取這支竿的元端行為分類。兩支解算器共用，確保判定一致。"""
    return classify_butt_behaviour(
        rod_data.get("basic_specifications", {}).get("Butt_Diameter_mm"),
        rod_data.get("taper_action_analysis", {}).get("Butt_Excess_Index"))


def calculate_bending_curve_45deg(rod_data, load_g, num_points=300):
    specs = rod_data["basic_specifications"]
    params = rod_data["curve_plotting_parameters"]
    mat_info = rod_data.get("material_and_structure_effects", {})
    return solve_bending_45deg(
        length_cm=parse_length_cm(specs.get("Length")),
        tip_dia=require_spec(specs, "Tip_Diameter_mm"),
        butt_dia=require_spec(specs, "Butt_Diameter_mm"),
        p_flex0=require_spec(params, "initial_flex_point_pct") / 100.0,
        k_power=require_spec(params, "power_stiffness_factor"),
        mu_tip=float(params.get("tip_flexibility_multiplier") or 1.0),
        mu_butt=float(params.get("butt_stiffness_multiplier") or 1.0),
        is_solid_tip="Solid Tip" in (mat_info.get("Tip_Structure") or ""),
        load_g=load_g,
        butt_behaviour=rod_butt_behaviour(rod_data),
        num_points=num_points,
    )


def get_dynamic_load_list(lure_str):
    """依該竿的額定負載上限推演階梯，最後補一個固定的搏魚極端值。

    負載區間必須跟著竿子走——0.6〜5g 的 UL 竿與 11〜28g 的 H 竿，
    合理的取樣點差了一個數量級，套同一組固定克數毫無意義。
    """
    min_lure, max_lure = parse_lure_range_g(lure_str)
    if max_lure is None or max_lure <= 0:
        raise ValueError("無法從 {!r} 解析路亞負載上限；請重跑 extract。".format(lure_str))
    if min_lure is None or min_lure <= 0 or min_lure >= max_lure:
        min_lure = max_lure * LOAD_LADDER_FALLBACK_MIN_RATIO

    start = min_lure * LOAD_LADDER_START_RATIO
    ratio = (max_lure / start) ** (1.0 / (LOAD_LADDER_STEPS - 1))
    loads = [round(start * (ratio ** i), 1) for i in range(LOAD_LADDER_STEPS)]
    loads[-1] = round(max_lure, 1)  # 最後一段必須剛好落在額定上限

    # 額定上限之上再加一個超額點。上限本身保留，因為那是對齊原廠建議的錨點。
    loads.append(round(max_lure * LOAD_OVERLOAD_RATIO, 1))

    # 搏魚值只在它真的高於額定上限時才有意義——對額定 120g 的竿來說，100g
    # 落在工作範圍內，不是什麼極端負載。
    # 🔴 不得用 `x < FIGHT_LOAD_G` 過濾整個階梯：那會把額定上限本身砍掉
    #    （額定 60〜120g 的竿，120 與超額點 138 都會消失）。
    if FIGHT_LOAD_G > max_lure:
        loads.append(FIGHT_LOAD_G)

    loads = sorted(set(loads))
    return [int(x) if x == int(x) else x for x in loads]


def load_role(load_g, max_lure):
    """這個負載在圖上的角色：額定內／超額／搏魚。決定顏色、線型與標籤。"""
    if load_g == FIGHT_LOAD_G:
        return "fight"
    if max_lure is not None and load_g > max_lure:
        return "overload"
    return "rated"

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

    bounds = [0.0, 0.0, 0.0, 0.0]  # min_x, max_x, min_y, max_y
    for idx, rod in enumerate(rod_list):
        model_name, color = rod["model_name"], get_rod_color(idx, len(rod_list))
        X, Y = calculate_bending_curve_45deg(rod, load_g)
        ax.plot(X, Y, label=model_name, color=color, linewidth=2.0, zorder=4)
        bounds = [min(bounds[0], float(np.min(X))), max(bounds[1], float(np.max(X))),
                  min(bounds[2], float(np.min(Y))), max(bounds[3], float(np.max(Y)))]

    # Apply dedicated margins: Top 15% for title, Right 25% for info/legend
    plt.subplots_adjust(left=0.05, right=0.75, top=0.85, bottom=0.05)

    # Global Title at the very top
    # 🔴 標題不得寫死廠牌或系列名（原本是 "HEARTLAND ..."）——
    #    本腳本不知道進來的是哪個系列，寫死等於在圖上宣告一個沒查證的事實。
    fig.suptitle(f"{category_name} COMPARISON", fontsize=24, color="#333333", fontweight='bold')

    # Load Box in the right margin
    props = dict(boxstyle="square,pad=0.5", facecolor="black", edgecolor="black")
    fig.text(0.87, 0.85, f"Load\n{load_g}\ngram", fontsize=16, color="white", fontweight='bold', ha='center', va='top', bbox=props)

    # 🔴 範圍必須涵蓋所有畫出來的幾何。原本只追蹤 min_x 與 max_y，
    #    重負載下竿子彎過垂直、曲線往下走，就會被裁掉一整段（看起來像算錯）。
    pad = 0.06 * max(bounds[1] - bounds[0], bounds[3] - bounds[2], 1.0)
    ax.set_xlim(bounds[0] - pad, max(10.0, bounds[1] + pad))
    ax.set_ylim(bounds[2] - pad, bounds[3] + pad)
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
    # 標籤與工程圖一致：額定內只寫克數，超出額定與搏魚要點名，
    # 否則讀者看不出哪一條已經超過原廠建議負載。
    _, max_lure = parse_lure_range_g(rod.get("basic_specifications", {}).get("Lure_Rating"))
    bounds = [0.0, 0.0, 0.0, 0.0]  # min_x, max_x, min_y, max_y
    for i, load_g in enumerate(load_list):
        color = cmap(i / max(1, len(load_list)-1))
        role = load_role(load_g, max_lure)
        label = {"fight": "搏魚 {:g}g", "overload": "超額 {:g}g"}.get(role, "{:g}g").format(load_g)
        X, Y = calculate_bending_curve_45deg(rod, load_g)
        ax.plot(X, Y, label=label, color=color, linewidth=2.0, zorder=4)
        ax.scatter([X[-1]], [Y[-1]], color=color, s=20, zorder=5)
        bounds = [min(bounds[0], float(np.min(X))), max(bounds[1], float(np.max(X))),
                  min(bounds[2], float(np.min(Y))), max(bounds[3], float(np.max(Y)))]

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
    # 與工程圖用語一致：都叫「額定負載」，不要一邊寫 Lure 一邊寫額定。
    if lure_str: fig.text(0.87, 0.65, f"額定負載 {sanitize_text(lure_str)}", fontsize=11, color="#555555", ha='center', va='center')

    # 🔴 範圍必須涵蓋所有畫出來的幾何。原本只追蹤 min_x 與 max_y，
    #    重負載下竿子彎過垂直、曲線往下走，就會被裁掉一整段（看起來像算錯）。
    pad = 0.06 * max(bounds[1] - bounds[0], bounds[3] - bounds[2], 1.0)
    ax.set_xlim(bounds[0] - pad, max(10.0, bounds[1] + pad))
    ax.set_ylim(bounds[2] - pad, bounds[3] + pad)
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
        for load_g in COMPARISON_LOADS_G:
            plot_zenaq_comparison(rods, name, load_g, output_dir)

    for rod in rod_dataset:
        lure_str = rod.get("basic_specifications", {}).get("Lure_Rating")
        plot_zenaq_progressive(rod, get_dynamic_load_list(lure_str), output_dir)

    print("[SUCCESS] All ZENAQ-style plots generated successfully!")

# ==========================================
# ENGINEERING STYLE PHYSICS & PLOTS
# ==========================================
# 水平版竿尖轉角的軟上限（度）。原始腳本用 tanh 做 C∞ 平滑鉗制，
# 曲線因此永遠不可能捲起來，同時保留飽和前的完整層次。
MAX_TIP_ANGLE_DEG = 82.0


def calculate_bending_curve_horizontal(rod_data, load_g, num_points=300):
    """水平 0 度起始的工程版彎曲曲線。

    🔴 這一套與 45 度版是**不同的物理模型**，不是換個角度而已：
       ・剛度用 (d/d_butt)^2.2 並設下限 0.08（正則化，避免細竿尖除爆）
       ・彎曲區以高斯峰表示，並依 eta_shift 隨負載往元端移動
       ・實心竿先用 sigmoid 在 s≥0.84 處軟化；3DX 元端補強獨立處理
       ・力量對負載是次線性（load^0.72），壓縮 100〜1000g 的跨度
       ・theta 以 tanh 軟鉗制在 82 度
    先前 repo 版把這些全部換成 45 度解算器的複製品（只把力量係數減半），
    等於丟掉整套模型。此處依 generate_bending_curves.py 的原始實作還原。
    """
    specs = rod_data["basic_specifications"]
    params = rod_data["curve_plotting_parameters"]
    mat_info = rod_data.get("material_and_structure_effects", {})

    length_cm = parse_length_cm(specs.get("Length"))
    tip_dia = require_spec(specs, "Tip_Diameter_mm")
    butt_dia = require_spec(specs, "Butt_Diameter_mm")
    p_flex0 = require_spec(params, "initial_flex_point_pct") / 100.0
    k_power = require_spec(params, "power_stiffness_factor")
    eta_shift = float(params.get("load_transition_shift_rate") or 0.35)
    mu_tip = float(params.get("tip_flexibility_multiplier") or 1.0)
    mu_butt = float(params.get("butt_stiffness_multiplier") or 1.0)

    tip_struct = mat_info.get("Tip_Structure") or ""
    is_solid_tip = "Solid Tip" in tip_struct
    butt_struct = mat_info.get("Butt_Structure") or ""
    is_reinforced_butt = ("3DX" in butt_struct) and ("Excluded" not in butt_struct)

    ds = length_cm / (num_points - 1)
    s_norm = np.linspace(0.0, 1.0, num_points)  # 0 = 元端，1 = 竿先

    # 1. 基礎斷面剛度（正則化，避免極細竿尖讓 compliance 爆掉）
    dia_profile = butt_dia - (butt_dia - tip_dia) * s_norm
    i_base = np.maximum((dia_profile / butt_dia) ** 2.2, 0.08)

    # 2. 彎曲區隨負載往元端移動
    load_ratio = load_g / 1000.0
    flex_shift = eta_shift * (load_ratio ** 0.6) * 0.25
    u_flex = np.clip((1.0 - p_flex0) - flex_shift, 0.20, 0.85)
    sigma_flex = 0.15 + 0.10 * load_ratio
    compliance_flex = 1.0 + 1.4 * np.exp(-(((s_norm - u_flex) / sigma_flex) ** 2))

    # 3. 竿先結構
    if is_solid_tip:
        tip_compliance = 1.0 + (mu_tip * 1.6 - 1.0) / (1.0 + np.exp(-(s_norm - 0.84) / 0.03))
    else:
        tip_compliance = 1.0 + (mu_tip - 1.0) * (s_norm ** 2)

    # 4. 元端補強
    if is_reinforced_butt:
        butt_stiffness = 1.0 + 0.35 * np.exp(-((s_norm / 0.40) ** 2))
    elif mu_butt != 1.0:
        butt_stiffness = 1.0 + (mu_butt - 1.0) * np.exp(-((s_norm / 0.35) ** 2))
    else:
        butt_stiffness = np.ones(num_points)

    compliance = (compliance_flex * tip_compliance) / (i_base * k_power * butt_stiffness)

    # 與 45 度解算器共用同一個絕對剛度判定，兩張圖的彎曲分佈才不會互相矛盾。
    compliance = apply_butt_behaviour(compliance, rod_butt_behaviour(rod_data))

    # 🟡 同樣是經驗校準的力量係數，非物理推導。
    force_mag = 0.0000018 * (load_g ** 0.72) / (k_power ** 0.45)

    max_theta = math.radians(MAX_TIP_ANGLE_DEG)
    X = np.linspace(0.0, length_cm, num_points)
    Y = np.zeros(num_points)
    theta = np.zeros(num_points)

    for _ in range(8):
        moment_arm = np.maximum(0.0, X[-1] - X)
        curvature = force_mag * moment_arm * np.clip(np.cos(theta), 0.0, 1.0) * compliance

        # 梯形積分求斜角，再以 tanh 平滑鉗制
        d_theta = 0.5 * (curvature[:-1] + curvature[1:]) * ds
        theta = np.concatenate(([0.0], np.cumsum(d_theta)))
        theta = max_theta * np.tanh(theta / max_theta)

        avg_theta = 0.5 * (theta[:-1] + theta[1:])
        x_new = np.concatenate(([0.0], np.cumsum(ds * np.cos(avg_theta))))
        y_new = np.concatenate(([0.0], np.cumsum(-ds * np.sin(avg_theta))))

        X = 0.5 * X + 0.5 * x_new
        Y = 0.5 * Y + 0.5 * y_new
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

    # 🔴 負載必須跟著這支竿的額定走，不得寫死克數。
    #    原本固定 100/250/500/1000g，套在 702UL+FS-ST23（額定 0.6〜5g）上
    #    就是 20×／50×／100×／200× 額定——那不是彎曲曲線，是把竿子折斷的模擬。
    #    與 progressive 圖共用同一組階梯：兩種圖只差在持竿角度，負載定義必須一致。
    ladder = get_dynamic_load_list(specs.get("Lure_Rating"))
    _, max_lure = parse_lure_range_g(specs.get("Lure_Rating"))
    cmap = plt.get_cmap("viridis")
    rated = [x for x in ladder if load_role(x, max_lure) == "rated"]
    loads = []
    for load_g in ladder:
        role = load_role(load_g, max_lure)
        if role == "fight":
            loads.append((load_g, "搏魚 ({:g}g)".format(load_g), "#d62728", "-", 2.8))
        elif role == "overload":
            loads.append((load_g, "超額 ({:g}g)".format(load_g), "#ff7f0e", "--", 2.2))
        else:
            shade = cmap(0.12 + 0.62 * rated.index(load_g) / max(1, len(rated) - 1))
            loads.append((load_g, "{:g}g".format(load_g), shade, "-", 1.8))

    # 圖表區退到左側，右側留一整欄放圖例與資訊——與 ZENAQ 兩種圖的版面一致。
    # 原本圖例壓在座標軸右上角，會蓋住輕負載曲線的尾段。
    fig, ax = plt.subplots(figsize=(15, 7), dpi=300)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fcfcfc")
    fig.subplots_adjust(left=0.06, right=0.66, top=0.88, bottom=0.10)

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

    # ---- 右欄：額定負載 → 圖例 → 規格／參數 ----
    # 原廠建議負載獨立標出來，讀者才分得出哪幾條在額定內、哪一條超額、哪一條搏魚。
    # 座標軸頂端在 figure 的 0.88，所以這一行要放在其上方才不會壓到圖例；
    # 主標題置中於左側圖表區，右欄在這個高度是空的。
    fig.text(0.68, 0.935, "額定負載 {}".format(show_or_missing(specs.get("Lure_Rating"))),
             fontsize=11, fontweight="bold", color="#333333", va="top", family="sans-serif")

    ax.legend(loc="upper left", bbox_to_anchor=(1.03, 1.0), frameon=False,
              fontsize=9.5, borderaxespad=0.0)

    props = dict(boxstyle="round,pad=0.6", facecolor="#ffffff", edgecolor="#cccccc", alpha=0.92)
    fig.text(0.68, 0.55, info_text, fontsize=8.5, va="top", bbox=props, family="sans-serif")

    out_path = os.path.join(output_dir, "Engineering_Curves", f"{model_name}_Engineering.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # 🔴 不可用 bbox_inches='tight'：它會依內容重新裁切，讓上面 subplots_adjust
    #    訂好的欄寬失效，右欄的文字位置就會跑掉。
    fig.savefig(out_path, dpi=300)
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
