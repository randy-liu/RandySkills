# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "numpy",
#     "pillow",
# ]
# ///
"""由官方商品圖量測釣竿的握把長度與可利用竿長。

🔴 **本腳本只做「從圖量長度」。量不出來時回報失敗，絕不輸出估計值。**
   理由見 README.md：同樣 218cm 的六支竿，握把從 30.1 到 40.8cm，
   任何依全長回填的公式都只是把雜訊寫進下游的圖裡。
"""
import argparse
import io
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

import numpy as np
from PIL import Image, ImageDraw

# UTF-8 輸出。stderr 也要設——錯誤訊息是中文，Windows 主控台預設 cp950 會炸掉，
# 而炸掉的正好是「為什麼量不出來」那一段，等於把最需要看到的訊息弄丟。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


# ============================================================
# 常數
# ============================================================

BG_PERCENTILE = 95          # 背景亮度取這個百分位（商品圖是白底）
BAND_DARK_MARGIN = 45       # 比背景暗這麼多才算「有東西」（切帶用）
COL_DARK_MARGIN = 40        # 該行有沒有竿身（量厚度用）
BAND_MIN_COVER = 0.05       # 一條帶至少要橫跨 5% 影像寬，否則是雜訊

# 握把前緣＝厚度 ≥ 0.6×最大值、且**連續**夠長的最外緣。
GRIP_THRESH_RATIO = 0.60
# 🔴 **這個「連續」條件不可省。** 導環會造成單點厚度尖峰；第一版沒有這個條件時，
#    722MLRSS-24 被量成 96.5cm（真值 34.5cm）——被最大導環騙了。
GRIP_MIN_RUN_FRAC = 0.012

# 合理性檢查：握把佔全長的比例。實測 12 支落在 12.8〜18.7%。
# 🔴 這裡比下游 rod-curve-generator 的 30% 護欄更嚴——**生產端就該擋掉，
#    不要讓壞資料走到只剩最後一道防線**。
GRIP_FRAC_MIN = 0.10
GRIP_FRAC_MAX = 0.25

CROSS_CHECK_TOL = 0.35      # 交叉檢查容許的相對誤差（半高門檻本身有 ±10% 的系統偏差）
EVA_GRIP_MM_RANGE = (18.0, 32.0)


class MeasurementError(Exception):
    """量測失敗。`stage` 說明卡在哪一層——這是回報時必須講清楚的東西。"""

    def __init__(self, stage, message):
        super().__init__(message)
        self.stage = stage
        self.message = message


# ============================================================
# 影像取得
# ============================================================

def load_image(src, timeout=30):
    """讀入商品圖。src 可以是本機路徑或網址。

    🔴 拿不到圖時**必須**丟 MeasurementError，不得回傳 None 讓呼叫端繼續往下走。
       「圖拿不到」與「圖解析不出」是兩種不同的結局，要分開講。
    """
    if re.match(r"^https?://", src, re.IGNORECASE):
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "rod-grip-measurer"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise MeasurementError("取得圖片", "下載失敗：{}（{}）".format(src, exc))
        try:
            return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as exc:
            raise MeasurementError("取得圖片",
                                   "下載到的內容不是圖片：{}（{} bytes，{}）"
                                   .format(src, len(raw), exc))
    if not os.path.exists(src):
        raise MeasurementError("取得圖片", "找不到檔案：{}".format(src))
    try:
        return Image.open(src).convert("RGB")
    except Exception as exc:
        raise MeasurementError("取得圖片", "讀不了這個檔案：{}（{}）".format(src, exc))


# ============================================================
# 影像分析
# ============================================================

def luminance(img):
    return np.asarray(img).astype(float).mean(axis=2)


def find_bands(lum, bg):
    """逐列統計暗像素，切出水平帶（每一帶＝竿子的一節）。"""
    width = lum.shape[1]
    on = (lum < bg - BAND_DARK_MARGIN).sum(axis=1) > width * BAND_MIN_COVER
    bands, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            bands.append((start, i - 1))
            start = None
    if start is not None:
        bands.append((start, len(on) - 1))
    return bands


def thickness_profile(lum, y0, y1, bg):
    """逐行量竿身厚度（像素）。

    🔴 用 **half-max**（背景與該行最暗值的中點）而不是固定門檻：
       不同商品圖的曝光與壓縮程度不同，固定門檻在深色圖上會把竿身量胖。
    """
    out = np.zeros(lum.shape[1])
    for x in range(lum.shape[1]):
        col = lum[y0:y1 + 1, x]
        if col.min() > bg - COL_DARK_MARGIN:
            continue
        half = (bg + col.min()) / 2.0
        idx = np.nonzero(col < half)[0]
        if len(idx):
            out[x] = idx.max() - idx.min() + 1
    return out


def sustained_runs(mask, min_len):
    """回傳 mask 中長度 ≥ min_len 的連續區段。"""
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                out.append((start, i - 1))
            start = None
    if start is not None and len(mask) - start >= min_len:
        out.append((start, len(mask) - 1))
    return out


def measure_image(img, length_cm, closed_cm=None, tip_dia_mm=None, butt_dia_mm=None):
    """量出握把長度與可利用竿長。回傳 dict；量不出來時丟 MeasurementError。"""
    lum = luminance(img)
    bg = float(np.percentile(lum, BG_PERCENTILE))
    bands = find_bands(lum, bg)

    if not bands:
        raise MeasurementError("切帶", "圖上找不到任何竿身——背景判定或影像本身有問題。")
    if len(bands) > 2:
        raise MeasurementError(
            "切帶",
            "切出 {} 條帶（預期 1 或 2）。這張圖可能不是標準商品圖，"
            "或含有其他物件。**不猜**，請改用單純的商品圖。".format(len(bands)))

    profiles = [thickness_profile(lum, b[0], b[1], bg) for b in bands]
    butt_i = int(np.argmax([p.max() for p in profiles]))
    t_butt = profiles[butt_i]
    cols_butt = np.nonzero(t_butt > 0)[0]
    if len(cols_butt) < 10:
        raise MeasurementError("切帶", "元節太短或偵測不到，無法量測。")
    butt_px = int(cols_butt.max() - cols_butt.min() + 1)

    # 比例尺：拆節圖用仕舞寸法，整支組裝圖用全長。
    if len(bands) == 2:
        if not closed_cm:
            raise MeasurementError(
                "比例尺",
                "這是拆成兩節的商品圖，比例尺要用官方仕舞寸法，但沒有提供 --closed-cm。")
        photo_kind = "拆節平放"
        scale = butt_px / float(closed_cm)
        scale_basis = "元節 {}px ÷ 仕舞寸法 {}cm".format(butt_px, closed_cm)
    else:
        photo_kind = "整支組裝"
        scale = butt_px / float(length_cm)
        scale_basis = "全長 {}px ÷ 全長 {}cm".format(butt_px, length_cm)

    # 握把前緣：厚度 ≥ 0.6×最大、且連續夠長的最外緣（靠竿尖那一側）。
    thresh = GRIP_THRESH_RATIO * t_butt.max()
    min_run = max(3, int(GRIP_MIN_RUN_FRAC * butt_px))
    runs = sustained_runs(t_butt >= thresh, min_run)
    if not runs:
        raise MeasurementError(
            "找握把",
            "找不到連續夠長的粗段（門檻 {:.0f}px、需連續 {}px）——"
            "這張圖裡可能沒有握把，或握把與竿身的粗細落差太小。".format(thresh, min_run))

    peak_x = int(np.argmax(t_butt))
    grip_at_right = abs(peak_x - cols_butt.max()) < abs(peak_x - cols_butt.min())
    if grip_at_right:
        front = min(r[0] for r in runs)
        grip_px = cols_butt.max() - front + 1
        blank_win = (max(cols_butt.min(), front - int(0.03 * butt_px)), front - 2)
    else:
        front = max(r[1] for r in runs)
        grip_px = front - cols_butt.min() + 1
        blank_win = (front + 2, min(cols_butt.max(), front + int(0.03 * butt_px)))

    grip_cm = grip_px / scale
    usable_cm = length_cm - grip_cm
    grip_frac = grip_cm / length_cm

    result = {
        "photo_kind": photo_kind,
        "bands": bands,
        "butt_band": bands[butt_i],
        "butt_px": butt_px,
        "scale_px_per_cm": scale,
        "scale_basis": scale_basis,
        "grip_front_x": int(front),
        "grip_at_right": grip_at_right,
        "grip_cm": grip_cm,
        "grip_frac": grip_frac,
        "usable_cm": usable_cm,
        "usable_frac": usable_cm / length_cm,
        "length_cm": length_cm,
        "closed_cm": closed_cm,
        "checks": cross_checks(profiles, butt_i, bands, blank_win, scale,
                               length_cm, closed_cm, tip_dia_mm, butt_dia_mm),
    }

    # 🔴 合理性檢查放在最後、而且會直接讓量測失敗。
    #    數字不合理就不要輸出——下游對「沒有量測值」已有正確處理。
    if not (GRIP_FRAC_MIN <= grip_frac <= GRIP_FRAC_MAX):
        raise MeasurementError(
            "合理性檢查",
            "量到握把 {:.1f}cm，佔全長 {:.1f}%，落在合理範圍 {:.0f}〜{:.0f}% 之外。"
            "\n       八成是偵測抓錯（比例尺錯、抓錯帶、或這張圖不是標準商品圖）。"
            "\n       **不輸出數值**，請人工檢視複驗圖後再決定。"
            .format(grip_cm, 100 * grip_frac, 100 * GRIP_FRAC_MIN, 100 * GRIP_FRAC_MAX))
    return result


def cross_checks(profiles, butt_i, bands, blank_win, scale, length_cm,
                 closed_cm, tip_dia_mm, butt_dia_mm):
    """比例尺的交叉檢查。資料不足的項目回報「無法檢查」，不是「失敗」。"""
    checks = []
    t_butt = profiles[butt_i]

    def add(name, measured, expected, unit="mm", note=""):
        if measured is None or expected is None:
            checks.append({"name": name, "status": "無法檢查", "note": note})
            return
        rel = abs(measured - expected) / expected
        checks.append({
            "name": name, "measured": measured, "expected": expected, "unit": unit,
            "status": "✅" if rel <= CROSS_CHECK_TOL else "⚠️",
            "rel": rel, "note": note,
        })

    # 竿尖最細處 vs 官方先径
    tip_mm = None
    tip_note = ""
    if len(bands) == 2:
        t_tip = profiles[1 - butt_i]
        cols = np.nonzero(t_tip > 0)[0]
        if len(cols) > 20:
            edge = max(5, int(0.02 * len(cols)))
            head = t_tip[cols.min():cols.min() + edge].min()
            tail = t_tip[cols.max() - edge:cols.max()].min()
            tip_px = float(min(head, tail))
            # 🔴 低解析圖（約 9 px/cm）的 1.6mm 竿尖只有 1.3px，量不到。
            #    那是偵測極限，不是竿子的問題——報「無法檢查」而不是「檢查失敗」。
            if tip_px >= 2.0 and scale / 10.0 >= 0.15:
                tip_mm = tip_px / scale * 10.0
            else:
                tip_note = "解析度不足（{:.2f} px/mm），竿尖細到量不出來".format(scale / 10.0)
    else:
        tip_note = "整支組裝圖，竿尖與元節在同一條帶上，未分離量測"
    add("竿尖最細處 vs 官方先径", tip_mm, tip_dia_mm, note=tip_note)

    # 握把前緣上方的裸竿身 vs 官方元径
    blank_mm = None
    lo, hi = blank_win
    if hi > lo:
        seg = t_butt[lo:hi + 1]
        seg = seg[seg > 0]
        if len(seg):
            blank_mm = float(np.median(seg)) / scale * 10.0
    add("握把前緣上方的裸竿身 vs 官方元径", blank_mm, butt_dia_mm)

    # EVA 握把最粗（常識範圍）
    eva_mm = float(t_butt.max()) / scale * 10.0
    lo_mm, hi_mm = EVA_GRIP_MM_RANGE
    checks.append({
        "name": "EVA 握把最粗（常識 {:.0f}〜{:.0f}mm）".format(lo_mm, hi_mm),
        "measured": eva_mm, "expected": None, "unit": "mm",
        "status": "✅" if lo_mm <= eva_mm <= hi_mm else "⚠️", "note": "",
    })

    # 兩節像素和 − 全長 ＝ 接管重疊
    if len(bands) == 2 and closed_cm:
        t_tip = profiles[1 - butt_i]
        cols = np.nonzero(t_tip > 0)[0]
        tip_px = int(cols.max() - cols.min() + 1) if len(cols) else 0
        butt_cols = np.nonzero(t_butt > 0)[0]
        overlap = (tip_px + int(butt_cols.max() - butt_cols.min()) + 1) / scale - length_cm
        if overlap < 0:
            checks.append({
                "name": "接管重疊", "status": "無法檢查",
                # 這正是低解析圖的已知極限，寫清楚免得下次有人以為是 bug。
                "note": "算出負值 {:.1f}cm ＝ 竿尖節的細端偵測不到（低解析圖的已知極限）。"
                        "不影響元節與握把長度".format(overlap),
            })
        else:
            checks.append({
                "name": "接管重疊（應為正值、約 5〜8cm）", "measured": overlap,
                "expected": None, "unit": "cm",
                "status": "✅" if 2.0 <= overlap <= 12.0 else "⚠️", "note": "",
            })
    else:
        checks.append({"name": "接管重疊", "status": "無法檢查",
                       "note": "需要拆節圖與仕舞寸法"})
    return checks


# ============================================================
# 複驗圖
# ============================================================

def _caption_font(size):
    """找一個畫得出中文的字型。找不到就回 None，呼叫端改用純 ASCII 標題。

    🔴 **PIL 的預設點陣字型沒有中文字，中文標題會整排變成豆腐字。**
       圖上的字看不懂等於沒有字，而這張圖的用途正是「給人看」。
       所以：有字型就用中文，沒有就老實退回英文，不要硬畫。
    """
    from PIL import ImageFont
    candidates = [
        r"C:\Windows\Fonts\msjh.ttc", r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


def render_check(img, result, model, out_dir):
    """輸出複驗圖：元節放大，紅線畫在偵測到的握把前緣。

    🔴 這張圖**必須給人看過**。它是唯一能抓到「抓錯帶」「圖其實是組裝好的整支」
       這類錯誤的一步——數字看起來合理不代表抓對了位置。
    """
    os.makedirs(out_dir, exist_ok=True)
    y0, y1 = result["butt_band"]
    pad = max(4, (y1 - y0) // 4)
    crop = img.crop((0, max(0, y0 - pad), img.width, min(img.height, y1 + pad + 1)))
    scale = max(1, int(1600 / max(1, crop.width)))
    if scale > 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    # 標題列另外加在上方，不要壓在竿身上
    band_h = max(22, crop.height // 8)
    canvas = Image.new("RGB", (crop.width, crop.height + band_h), (255, 255, 255))
    canvas.paste(crop, (0, band_h))
    draw = ImageDraw.Draw(canvas)
    x = result["grip_front_x"] * scale
    draw.line([(x, 0), (x, canvas.height)], fill=(255, 0, 0), width=max(2, scale))
    font = _caption_font(max(13, band_h - 8))
    if font is not None:
        text = "{}　握把 {:.1f}cm（{:.1f}% 全長）　可利用竿長 {:.1f}cm　←紅線＝偵測到的前握把前緣".format(
            model, result["grip_cm"], 100 * result["grip_frac"], result["usable_cm"])
    else:
        text = "{}  grip {:.1f}cm ({:.1f}%)  usable {:.1f}cm  <- red line = detected grip front".format(
            model, result["grip_cm"], 100 * result["grip_frac"], result["usable_cm"])
    draw.text((6, 3), text, fill=(190, 0, 0), font=font)
    crop = canvas
    path = os.path.join(out_dir, "{}_grip_check.png".format(model.replace("+", "plus")))
    crop.save(path)
    return path


# ============================================================
# 寫回 rod-curve-generator 的量測表
# ============================================================

DEFAULT_TABLE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "rod-curve-generator", "references", "measured_grip_lengths.md")


def _parse_section_table(lines, section_prefix, key_col_hint):
    """回傳 (標題列索引, 分隔列索引, 資料列索引清單)。找不到就回 None。"""
    in_section = header = sep = None
    rows = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            if in_section is not None and header is not None:
                break
            in_section = line[3:].lstrip().startswith(section_prefix)
            header = sep = None
            rows = []
            continue
        if not in_section or not line.lstrip().startswith("|"):
            continue
        cells = [c.strip().strip("*`") for c in line.strip().strip("|").split("|")]
        if header is None:
            if len(cells) >= 4 and key_col_hint in cells[3]:
                header = i
            continue
        if sep is None:
            sep = i
            continue
        rows.append(i)
    return None if header is None else (header, sep, rows)


def write_into_table(table_path, model, category, length_cm, grip_cm, scale,
                     usable_cm, force=False):
    """把量測結果插進 §1 與 §1-b 兩張表。回傳 (原始內容, 新內容)。"""
    with open(table_path, encoding="utf-8") as fh:
        original = fh.read()
    lines = original.split("\n")

    found = _parse_section_table(lines, "1. ", "握把")
    if not found:
        raise MeasurementError(
            "寫入量測表",
            "在 {} 找不到 §1 的量測表（第 4 欄需含「握把」）。表格格式可能被改過。"
            .format(table_path))
    header, sep, rows = found

    existing = {}
    for i in rows:
        cells = [c.strip().strip("*`") for c in lines[i].strip().strip("|").split("|")]
        existing[cells[0]] = i
    if model in existing and not force:
        raise MeasurementError(
            "寫入量測表",
            "{} 已經在表裡了。要覆寫請加 --force（覆寫前請先確認新舊值差在哪）。".format(model))

    row1 = "| {} | {} | {:.0f} | **{:.1f}** | {:.1f}% | {:.2f} px/cm |".format(
        model, category or "?", length_cm, grip_cm, 100 * grip_cm / length_cm, scale)
    row2 = "| {} | {:.0f} | {:.1f} | **{:.1f}** | {:.1f}% |".format(
        model, length_cm, grip_cm, usable_cm, 100 * usable_cm / length_cm)

    def splice(all_lines, section_prefix, hint, new_row, sort_col):
        f = _parse_section_table(all_lines, section_prefix, hint)
        if not f:
            return all_lines, False
        _h, _s, _rows = f
        keep = [j for j in _rows
                if [c.strip().strip("*`")
                    for c in all_lines[j].strip().strip("|").split("|")][0] != model]
        block = [all_lines[j] for j in keep] + [new_row]

        def sort_key(line):
            cells = [c.strip().strip("*`") for c in line.strip().strip("|").split("|")]
            try:
                return float(cells[sort_col])
            except (ValueError, IndexError):
                return 0.0
        block.sort(key=sort_key)
        return all_lines[:_rows[0]] + block + all_lines[_rows[-1] + 1:], True

    lines, ok1 = splice(lines, "1. ", "握把", row1, 3)
    lines, _ok2 = splice(lines, "1-b", "可利用竿長", row2, 2)
    if not ok1:
        raise MeasurementError("寫入量測表", "§1 表格插入失敗。")

    new_text = "\n".join(lines)
    with open(table_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new_text)
    return original, new_text


def reparse_check(table_path, model, grip_cm, expected_count):
    """寫完之後自己再讀一次，確認讀回來的真的是握把、而且筆數對。

    🔴 **這一道是主要的把關，不是 validate_ccs。** 曾經發生過：在這個檔案裡加了
       第二張同形狀的表，解析器讀成別欄，12 張圖全部畫錯而且沒有任何錯誤訊息。
       寫入端自己驗一次，比依賴下游的測試能跑起來更可靠。
    """
    table = {}
    with open(table_path, encoding="utf-8") as fh:
        in_section = header_seen = False
        for line in fh:
            if line.startswith("## "):
                in_section = line[3:].lstrip().startswith("1.")
                header_seen = False
                continue
            if not in_section or not line.lstrip().startswith("|"):
                continue
            cells = [c.strip().strip("*`") for c in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            if not header_seen:
                header_seen = "握把" in cells[3]
                continue
            try:
                table[cells[0]] = float(cells[3])
            except ValueError:
                continue
    problems = []
    if len(table) != expected_count:
        problems.append("筆數 {}，預期 {}".format(len(table), expected_count))
    if model not in table:
        problems.append("讀不到剛寫入的 {}".format(model))
    elif abs(table[model] - grip_cm) > 0.05:
        problems.append("{} 讀回來是 {}，寫入的是 {:.1f}".format(model, table[model], grip_cm))
    bad = {m: g for m, g in table.items() if not (15.0 <= g <= 60.0)}
    if bad:
        problems.append("有值不在 15〜60cm：{}".format(bad))
    return problems, table


def run_validate_ccs():
    """跑下游的回歸測試並回傳 (是否跑得起來, 輸出)。跑不起來不算寫入失敗。"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                          "rod-curve-generator", "scripts", "validate_ccs.py")
    if not os.path.exists(script):
        return False, "找不到 {}".format(script)
    for cmd in (["uv", "run", script], [sys.executable, script]):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", timeout=300)
        except (OSError, subprocess.SubprocessError):
            continue
        out = (proc.stdout or "") + (proc.stderr or "")
        if "握把表" in out:
            return True, out
    return False, ("validate_ccs.py 跑不起來（可能缺 numpy／matplotlib，"
                   "或這個環境沒有 uv）。請自行執行一次確認。")


# ============================================================
# CLI
# ============================================================

def cmd_measure(args):
    img = load_image(args.image)
    result = measure_image(img, args.length_cm, args.closed_cm,
                           args.tip_dia_mm, args.butt_dia_mm)
    check_png = render_check(img, result, args.model, args.out_dir)

    print("=" * 66)
    print("{}　握把與可利用竿長量測".format(args.model))
    print("=" * 66)
    print("圖型　　　{}（{} 條帶）".format(result["photo_kind"], len(result["bands"])))
    print("比例尺　　{:.2f} px/cm（{}）".format(result["scale_px_per_cm"], result["scale_basis"]))
    print("")
    print("握把＋輪座　　{:.1f} cm（佔全長 {:.1f}%）".format(
        result["grip_cm"], 100 * result["grip_frac"]))
    print("可利用竿長　　{:.1f} cm（佔全長 {:.1f}%）＝ 全長 {:.0f} − 握把 {:.1f}".format(
        result["usable_cm"], 100 * result["usable_frac"], args.length_cm, result["grip_cm"]))
    print("")
    print("比例尺交叉檢查：")
    for c in result["checks"]:
        if c["status"] == "無法檢查":
            print("  ⊘  {:<34} 無法檢查{}".format(
                c["name"], "：" + c["note"] if c.get("note") else ""))
        elif c.get("expected") is None:
            print("  {} {:<34} {:.2f} {}".format(c["status"], c["name"],
                                                 c["measured"], c["unit"]))
        else:
            print("  {} {:<34} 量到 {:.2f} vs 官方 {:.2f} {}（差 {:.0f}%）".format(
                c["status"], c["name"], c["measured"], c["expected"], c["unit"],
                100 * c["rel"]))
    print("")
    print("🔴 複驗圖：{}".format(check_png))
    print("   **請開圖確認紅線落在前握把前緣**。這是唯一能抓到「抓錯帶」的一步，")
    print("   數字看起來合理不代表位置抓對了。")

    print("")
    print("可貼進 measured_grip_lengths.md §1 的資料列：")
    print("| {} | {} | {:.0f} | **{:.1f}** | {:.1f}% | {:.2f} px/cm |".format(
        args.model, args.category or "?", args.length_cm, result["grip_cm"],
        100 * result["grip_frac"], result["scale_px_per_cm"]))

    if args.write:
        table_path = os.path.abspath(args.table or DEFAULT_TABLE)
        _, before_tbl = reparse_check(table_path, args.model, result["grip_cm"], -1)
        expected = len(before_tbl) + (0 if args.model in before_tbl else 1)
        original, _ = write_into_table(
            table_path, args.model, args.category, args.length_cm,
            result["grip_cm"], result["scale_px_per_cm"], result["usable_cm"],
            force=args.force)
        problems, _ = reparse_check(table_path, args.model, result["grip_cm"], expected)
        if problems:
            with open(table_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(original)
            raise MeasurementError(
                "寫入量測表",
                "寫入後自我複查失敗，**已回滾**：\n       - " + "\n       - ".join(problems))
        print("")
        print("✅ 已寫進 {}（§1 與 §1-b），複查通過（{} 筆）。".format(table_path, expected))
        # 🔴 validate_ccs 讀的是 rod-curve-generator 底下那張**固定路徑**的表。
        #    寫到別的檔卻去跑它，等於用另一個檔案的結果當這次寫入的背書——假訊號。
        if os.path.abspath(DEFAULT_TABLE) != table_path:
            print("   ⚠️ 這次寫的不是預設量測表，**略過下游回歸測試**"
                  "（它只讀 rod-curve-generator 底下那一張，跑了也不能證明這次寫入沒問題）。")
        else:
            ok, out = run_validate_ccs()
            for line in out.splitlines():
                if "握把表" in line:
                    print("   下游回歸測試：{}".format(line.strip()))
            if not ok:
                print("   ⚠️ {}".format(out.splitlines()[0] if out else "validate_ccs 未執行"))
        print("")
        print("🔴 **記得重畫圖**，否則磁碟上的圖還是舊的：")
        print("   uv run <rod-curve-generator>/scripts/rod_curve_cli.py plot-zenaq ...")
        print("   uv run <rod-curve-generator>/scripts/rod_curve_cli.py plot-engineering ...")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="由官方商品圖量測釣竿握把長度與可利用竿長")
    sub = parser.add_subparsers(dest="command", required=True)

    m = sub.add_parser("measure", help="量測單一型號")
    m.add_argument("--image", required=True, help="商品圖的本機路徑或網址")
    m.add_argument("--model", required=True, help="型號，例如 722MLRSS-24")
    m.add_argument("--length-cm", required=True, type=float, help="官方全長（公分）")
    m.add_argument("--closed-cm", type=float, help="官方仕舞寸法（公分）；拆節圖必填")
    m.add_argument("--tip-dia-mm", type=float, help="官方先径（mm），用於交叉檢查")
    m.add_argument("--butt-dia-mm", type=float, help="官方元径（mm），用於交叉檢查")
    m.add_argument("--category", help="S（紡車）或 B（貝爾）")
    m.add_argument("--out-dir", default=".", help="複驗圖輸出目錄")
    m.add_argument("--table", help="量測表路徑（預設為同層 rod-curve-generator 的）")
    m.add_argument("--write", action="store_true", help="寫進量測表並自我複查")
    m.add_argument("--force", action="store_true", help="型號已存在時允許覆寫")
    m.set_defaults(func=cmd_measure)

    args = parser.parse_args()
    try:
        return args.func(args)
    except MeasurementError as exc:
        # 🔴 失敗時**不輸出任何握把數值**，只講卡在哪一層。
        print("", file=sys.stderr)
        print("🔴 量測失敗｜卡在：{}".format(exc.stage), file=sys.stderr)
        print("   {}".format(exc.message), file=sys.stderr)
        print("", file=sys.stderr)
        print("   ⚠️ **不得改用估計值或公式回填。** 下游 rod-curve-generator 對「沒有量測值」",
              file=sys.stderr)
        print("      已有正確處理：會警告、圖上標「未量測」、且不套用握把剛性。",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
