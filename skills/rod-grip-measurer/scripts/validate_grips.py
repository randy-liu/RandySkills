# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "numpy",
#     "pillow",
# ]
# ///
"""回歸測試：拿 12 支已知答案的官方商品圖重量一次，比對記錄值。

🔴 **這個演算法騙過我一次。** 第一版沒有「連續」條件，`722MLRSS-24` 被最大導環的
   單點厚度尖峰騙成 96.5cm（真值 34.5cm）——數字大到離譜，但當下沒有任何東西擋它。
   所以偵測邏輯只要動到，就必須跑這支。

🔴 **本檔一律呼叫 `measure_grip.py` 自己的函式，不得另寫一份平行實作。**
   （`validate_ccs.py` 已有此前例。）平行實作會出現「測試過了但實際壞掉」的假訊號。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure_grip import (  # noqa: E402
    MeasurementError,
    load_image,
    measure_image,
)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                        "references", "reference_photos.md")

TOLERANCE_CM = 1.0


def _cells(line):
    return [c.strip().strip("*`") for c in line.strip().strip("|").split("|")]


def load_answer_key(path):
    """讀答案卷：規格＋期望值來自「答案卷」表，網址來自「官方商品圖網址」表。"""
    rods, urls = {}, {}
    with open(path, encoding="utf-8") as fh:
        section = None
        for line in fh:
            if line.startswith("## "):
                section = line[3:].strip()
                continue
            if not line.lstrip().startswith("|"):
                continue
            c = _cells(line)
            if section and section.startswith("答案卷") and len(c) >= 10:
                try:
                    rods[c[0]] = {
                        "category": c[1],
                        "length_cm": float(c[2]),
                        "closed_cm": None if c[3] in ("—", "-", "") else float(c[3]),
                        "tip_mm": float(c[4]),
                        "butt_mm": float(c[5]),
                        "photo_kind": c[6],
                        "grip_cm": float(c[7]),
                        "usable_cm": float(c[8]),
                    }
                except ValueError:
                    continue
            elif section and "網址" in section and len(c) >= 2:
                m = re.search(r"<(https?://[^>]+)>", c[1])
                if m:
                    urls[c[0]] = m.group(1)
    return rods, urls


def main():
    ap = argparse.ArgumentParser(description="握把量測的回歸測試")
    ap.add_argument("--image-dir",
                    help="改用本機目錄裡的圖（檔名 <型號>.jpg，`+` 換成 plus），不連網")
    args = ap.parse_args()

    rods, urls = load_answer_key(REF_PATH)
    if not rods:
        print("🔴 答案卷讀不到任何資料——references/reference_photos.md 的表格格式可能壞了。")
        return 1

    print("=" * 74)
    print("握把量測回歸測試（答案卷：{} 支）".format(len(rods)))
    print("=" * 74)
    print("%-16s %10s %10s %9s  %s" % ("型號", "記錄cm", "重量cm", "差", "圖型"))
    print("-" * 74)

    passed, failed, skipped = [], [], []
    for model, spec in sorted(rods.items(), key=lambda kv: kv[1]["grip_cm"]):
        if args.image_dir:
            src = os.path.join(args.image_dir, model.replace("+", "plus") + ".jpg")
            if not os.path.exists(src):
                src = os.path.join(args.image_dir, model + ".jpg")
        else:
            src = urls.get(model)
        if not src:
            skipped.append((model, "答案卷裡沒有這一支的網址"))
            print("%-16s %10.1f %10s %9s  SKIP（無網址）" % (model, spec["grip_cm"], "—", "—"))
            continue
        try:
            img = load_image(src)
            r = measure_image(img, spec["length_cm"], spec["closed_cm"],
                              spec["tip_mm"], spec["butt_mm"])
        except MeasurementError as exc:
            # 🔴 取不到圖 = SKIP（環境問題）；量得到圖卻量錯 = FAIL（程式問題）。
            #    兩者不可混為一談，否則「官網 404」會被誤讀成「演算法壞了」，反之亦然。
            if exc.stage == "取得圖片":
                skipped.append((model, exc.message))
                print("%-16s %10.1f %10s %9s  SKIP（%s）"
                      % (model, spec["grip_cm"], "—", "—", exc.stage))
            else:
                failed.append((model, "{}：{}".format(exc.stage, exc.message)))
                print("%-16s %10.1f %10s %9s  🔴 FAIL（%s）"
                      % (model, spec["grip_cm"], "—", "—", exc.stage))
            continue
        diff = r["grip_cm"] - spec["grip_cm"]
        ok = abs(diff) < TOLERANCE_CM and r["photo_kind"] == spec["photo_kind"]
        (passed if ok else failed).append(
            (model, "差 {:+.1f}cm".format(diff) if abs(diff) >= TOLERANCE_CM
             else "圖型判定 {} ≠ {}".format(r["photo_kind"], spec["photo_kind"])))
        print("%-16s %10.1f %10.1f %+9.2f  %s %s"
              % (model, spec["grip_cm"], r["grip_cm"], diff, r["photo_kind"],
                 "✅" if ok else "🔴"))

    print("-" * 74)
    print("通過 {}／失敗 {}／跳過 {}（門檻：誤差 < {:.1f}cm，且圖型判定一致）"
          .format(len(passed), len(failed), len(skipped), TOLERANCE_CM))

    if failed:
        print("")
        print("🔴 **未通過：**")
        for model, why in failed:
            print("   {:<16} {}".format(model, why))
        print("")
        print("   偵測邏輯壞了。請看複驗圖確認紅線位置，**不要調寬門檻讓它過**。")
        return 1

    if skipped:
        print("")
        print("⚠️ **有 {} 支被跳過，這不算通過。** 原因：".format(len(skipped)))
        for model, why in skipped:
            print("   {:<16} {}".format(model, why))
        print("")
        print("   官方換圖或無網路都會這樣。正確處置是回產品頁重抓網址並更新答案卷，")
        print("   **不是**把該支從答案卷裡刪掉。")
        if not passed:
            print("")
            print("🔴 全部跳過，等於什麼都沒測到。")
            return 1

    if not failed and not skipped:
        print("")
        print("✅ 全部通過（{}／{}）。".format(len(passed), len(rods)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
