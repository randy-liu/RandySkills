import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="釣竿幾何錐度運算 (Taper Ratio Calculation)")
    parser.add_argument("--tip", type=float, required=True, help="先徑 (Tip Dia) in mm")
    parser.add_argument("--butt", type=float, required=True, help="元徑 (Butt Dia) in mm")
    
    args = parser.parse_args()
    
    if args.tip <= 0:
        print("錯誤：先徑必須大於 0")
        sys.exit(1)
        
    ratio = args.butt / args.tip
    print(f"輸入數值: 先徑(Tip)={args.tip}mm, 元徑(Butt)={args.butt}mm")
    print(f"錐度比例 (Ratio) = {ratio:.2f}")
    print("-" * 30)
    
    if ratio >= 10.0:
        print("物理結構判定：極端高錐度 (EX-Fast)")
        print("說明：通常出現在微物竿或特殊底棲特化竿。")
    elif ratio >= 7.5:
        print("物理結構判定：Fast (先調子)")
        print("說明：彎曲點集中於前端，中肚具備高支撐力。")
    elif ratio < 7.0:
        print("物理結構判定：Regular / Slow (胴調子)")
        print("說明：粗細過渡平緩，受壓時均勻向後彎曲。")
    else:
        print("物理結構判定：中庸錐度 (Moderate Fast)")
        print("說明：介於 Fast 與 Regular 之間，具備適中的彎曲過渡。")

if __name__ == "__main__":
    main()
