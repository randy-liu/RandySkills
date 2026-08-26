# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy"]
# ///
"""彎曲形狀回歸測試：拿引擎去考 21 支已公佈 CCS Action Angle 的空白竿身。

資料來源、量測協定、以及每一條結論的推導，全部記載於
    references/ccs_calibration.md
本腳本只負責「算出來、對答案、印報表」，不解釋物理。

🔴 這 21 支是**別的廠牌的空白竿身**，僅供校準引擎的物理定律。
   **不得**把它們寫進任何一份釣竿分析報告，也不得作為任何受分析竿款的比較對象
   （`rod-spec-decrypter` 守則 3）。

用法：
    uv run <skill_dir>/scripts/validate_ccs.py
    uv run <skill_dir>/scripts/validate_ccs.py --exponent 4.0 --cap none --taper-power 1.0
"""
import argparse
import math
import os
import sys

import numpy as np

# =============================================================================
# 輸出編碼
# =============================================================================
# 與 calculate_taper.py 同樣的理由：Windows 主控台預設 cp950 編不出本腳本輸出的
# 「³」「⁴」與中文說明段，會在報表印到一半時拋 UnicodeEncodeError。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rod_curve_cli import solve_bending, START_ANGLE_HORIZONTAL  # noqa: E402

IN_MM = 25.4

# =============================================================================
# 答案卷
# =============================================================================
# Batson / Rainshadow ETERNITY RX10，21 支，全為空心。查證日 2026-08-25。
#   IP / AA  🟢 https://batsonenterprises.com/rainshadow-rod-blank-ccs-data
#   幾何規格 🟢 https://getbitoutdoors.com/blanks/rainshadow/eternity-rx10/
#
# ⚠️ `tip_64` 欄是**建議頂環尺寸**（1/64 吋），不是先徑量測值。頂環必須能套上竿尖，
#    故先徑略小於該值；此處以 TIP_SLACK_64 折算。這是假設，不是資料。
TIP_SLACK_64 = 0.25

# 型號, 全長(ft'in), 元徑(in), 頂環(64分), 自重(oz), 原廠調性標示, IP(g), AA(deg)
BLANKS = [
    ("ETEC68M-SS",    "6'8",  0.551, 4.5, 1.64, "Fast",     519, 75.0),
    ("ETEC68MH-SS",   "6'8",  0.550, 5.5, 1.88, "Fast",     662, 70.0),
    ("ETEC72M-SS",    "7'2",  0.552, 4.5, 2.03, "Fast",     597, 75.0),
    ("ETEC72MH-SS",   "7'2",  0.555, 5.5, 2.12, "Fast",     681, 72.0),
    ("ETEC74H-SS",    "7'4",  0.625, 6.0, 2.70, "Fast",     912, 70.0),
    ("ETEC76M-SS",    "7'6",  0.622, 5.0, 2.19, "Fast",     589, 76.0),
    ("ETEC76MH-SS",   "7'6",  0.632, 5.5, 2.45, "Fast",     753, 70.0),
    ("ETEC79H-SS",    "7'9",  0.653, 6.5, 3.55, "Fast",    1039, 70.0),
    ("ETES59ML-SS",   "5'9",  0.420, 4.5, 1.05, "Fast",     274, 67.5),
    ("ETES62L-SS",    "6'2",  0.345, 4.5, 1.20, "Fast",     258, 71.0),
    ("ETES62M-SS",    "6'2",  0.417, 4.5, 1.48, "Fast",     508, 74.0),
    ("ETES68L-SS",    "6'8",  0.356, 4.5, 1.46, "Fast",     264, 70.0),
    ("ETES68ML-SS",   "6'8",  0.480, 4.5, 1.40, "Fast",     312, 76.5),
    ("ETES68MXF-SS",  "6'8",  0.466, 4.5, 1.45, "X-Fast",   245, 71.5),
    ("ETES610MXF-SS", "6'10", 0.466, 4.5, 1.28, "X-Fast",   272, 74.5),
    ("ETES72L-SS",    "7'2",  0.367, 4.5, 1.70, "Fast",     273, 71.5),
    ("ETES72ML-SS",   "7'2",  0.487, 4.5, 1.77, "Fast",     343, 76.5),
    ("ETES72M-SS",    "7'2",  0.541, 4.5, 1.73, "Fast",     466, 75.0),
    ("ETES76ML-SS",   "7'6",  0.497, 4.5, 1.90, "Mod-Fast", 398, 81.5),
    ("ETES77M-SS",    "7'7",  0.550, 4.5, 1.90, "Fast",     500, 80.5),
    ("ETES79ML-SS",   "7'9",  0.489, 4.5, 1.65, "Fast",     302, 81.5),
]

# 目前已知的最佳擬合（見 references/ccs_calibration.md §3-3）。
# 🔴 指數 4.0 是**實測擬合出的有效指數，不是物理推導**。宣稱「壁厚正比於直徑所以是
#    四次方」是錯的——由公佈自重反推的壁厚已否證該假設（corr(k, 元徑) = −0.765）。
BEST_EXPONENT = 4.0
BEST_CLAMP_CM = 30.0
BEST_TAPER_POWER = 1.0

# RMS 驗收門檻。高於此值代表本次修改讓形狀變差，不得合入。
RMS_GATE_DEG = 5.0

# 幾何解釋不了的下限（見 §5）。追求低於此值＝在擬合雜訊。
IRREDUCIBLE_DEG = 4.0

N_POINTS = 160
SEP = "-" * 74


def feet(s):
    f, i = s.split("'")
    return (int(f) * 12 + float(i)) * 2.54


def action_angle(compliance, free_len_cm, target_drop_cm, n=N_POINTS):
    """CCS 協定：水平持竿，竿尖掛重，加到竿尖垂直下沉 target_drop 為止，讀竿尖傾角。

    AA 在一個**固定的撓曲量**下讀角度，所以竿子本身多硬會被自動抵銷——
    force scale 與 k_power 不影響結果。這正是它能拿來考引擎的原因。
    """
    lo, hi = 0.01, 1e9
    for _ in range(24):
        mid = math.sqrt(lo * hi)
        _, Y = solve_bending(free_len_cm, compliance, 1.0, mid,
                             START_ANGLE_HORIZONTAL, num_points=n)
        if abs(Y[-1]) < target_drop_cm:
            lo = mid
        else:
            hi = mid
    X, Y = solve_bending(free_len_cm, compliance, 1.0, hi,
                         START_ANGLE_HORIZONTAL, num_points=n)
    return math.degrees(math.atan2(-(Y[-1] - Y[-5]), X[-1] - X[-5]))


def build_profile(tip_mm, butt_mm, length_cm, taper_power, exponent, cap, clamp_cm,
                  n=N_POINTS):
    """夾持點之後的柔度剖面。夾持段不參與彎曲（CCS 要求竿子前 1 呎水平）。"""
    s = np.linspace(0.0, 1.0, n)
    clamped = clamp_cm / length_cm
    u = clamped + (1.0 - clamped) * s
    dia = tip_mm + (butt_mm - tip_mm) * ((1.0 - u) ** taper_power)
    c = 1.0 / dia ** exponent
    if cap:
        ceiling = c[0] * cap
        c = (c ** -3.0 + ceiling ** -3.0) ** (-1.0 / 3.0)
    return c / c.mean()


def sanity_check():
    """等剛度懸臂梁的解析解：撓曲 L/3 時竿尖傾角 = 1.5 × 1/3 = 0.5 rad = 28.6°。"""
    L = 213.0
    aa = action_angle(np.ones(N_POINTS), L, L / 3.0)
    ok = abs(aa - 28.6) < 3.0
    print(f"[驗證量法] 等剛度懸臂梁 AA = {aa:.1f}°（解析解 28.6°）  "
          f"{'✅ 量法正確' if ok else '🔴 量法有誤，以下結果全部不可信'}")
    return ok


def main():
    p = argparse.ArgumentParser(description="CCS Action Angle 回歸測試")
    p.add_argument("--exponent", type=float, default=BEST_EXPONENT,
                   help=f"柔度指數 1/d^n（預設 {BEST_EXPONENT}）")
    p.add_argument("--cap", default="none",
                   help="COMPLIANCE_RANGE 上限，或 none（預設 none）")
    p.add_argument("--taper-power", type=float, default=BEST_TAPER_POWER,
                   help=f"直徑剖面冪次（預設 {BEST_TAPER_POWER}）")
    p.add_argument("--clamp", type=float, default=BEST_CLAMP_CM,
                   help=f"元端夾持長度 cm（預設 {BEST_CLAMP_CM}）")
    args = p.parse_args()
    cap = None if str(args.cap).lower() in ("none", "0", "") else float(args.cap)

    print("=" * 74)
    print("彎曲形狀回歸測試 — CCS Action Angle")
    print("=" * 74)
    if not sanity_check():
        sys.exit(1)
    print(f"參數：指數 1/d^{args.exponent}  cap {args.cap}  "
          f"taper_power {args.taper_power}  夾持 {args.clamp:.0f}cm")
    print(SEP)
    print(f"{'空白竿身':16s} {'錐度比':>7s} {'公佈AA':>7s} {'模型':>7s} {'誤差':>7s}")

    est, pub = [], []
    for name, ln, butt_in, tip_64, _oz, _act, _ip, aa_pub in BLANKS:
        L = feet(ln)
        tip = (tip_64 - TIP_SLACK_64) / 64.0 * IN_MM
        butt = butt_in * IN_MM
        c = build_profile(tip, butt, L, args.taper_power, args.exponent, cap, args.clamp)
        a = action_angle(c, L - args.clamp, L / 3.0)
        est.append(a)
        pub.append(aa_pub)
        print(f"{name:16s} {butt/tip:7.2f} {aa_pub:7.1f} {a:7.1f} {a-aa_pub:+7.1f}")

    est, pub = np.array(est), np.array(pub)
    rms = float(np.sqrt(((est - pub) ** 2).mean()))
    bias = float((est - pub).mean())

    print(SEP)
    print(f"RMS 誤差   {rms:6.1f}°     （驗收門檻 {RMS_GATE_DEG:.0f}°）")
    print(f"平均偏差   {bias:+6.1f}°")
    print(f"模型跨距   {est.max()-est.min():6.1f}°    公佈跨距 {pub.max()-pub.min():.1f}°")
    print(f"相關係數   {np.corrcoef(est, pub)[0, 1]:+6.3f}")
    print("")

    if est.max() - est.min() < pub.max() - pub.min() - 6.0:
        print("🔴 **警示：模型跨距遠小於實測跨距——引擎對錐度差異缺乏鑑別力。**")
        print("    典型成因是柔度剖面被 cap 壓平；此時 RMS 就算勉強及格也不代表形狀畫對了。")
        print("")

    if rms > RMS_GATE_DEG:
        print(f"🔴 **未通過：RMS {rms:.1f}° 高於門檻 {RMS_GATE_DEG:.0f}°。**")
        print("    請勿以此組參數出圖，也不要為了通過而放寬門檻。")
        sys.exit(1)

    print(f"✅ 通過（RMS {rms:.1f}° ≤ {RMS_GATE_DEG:.0f}°）。")
    print("")
    print(SEP)
    print(f"⚠️  幾何解釋不了的下限約 ±{IRREDUCIBLE_DEG:.0f}°：碳布疊層與模數分佈無任何廠商公佈。")
    print("    實測中兩支錐度比相同的竿（8.30 vs 8.28）AA 差 5.5°。")
    print("    → 校準目標是**消除系統性偏差**，不是逐支吻合。追求逐支吻合等於擬合雜訊。")
    print("    → 本測試只驗證「形狀」。絕對撓曲量仍由經驗力量係數決定，依舊不可信。")


if __name__ == "__main__":
    main()
