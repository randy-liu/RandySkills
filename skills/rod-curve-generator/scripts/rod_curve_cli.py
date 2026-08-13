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

# Ensure UTF-8 output encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure fallback fonts for CJK characters
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# ==========================================
# PARSER LOGIC
# ==========================================
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

def parse_report_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        raw_content = f.read()
    clean_content = clean_markdown_tags(raw_content)
    model_name = os.path.basename(file_path).replace("_分析報告.md", "")
    
    if "先徑" not in raw_content and "先径" not in raw_content:
        print(f"[ERROR] '{os.path.basename(file_path)}' is missing crucial geometric data (先徑). Cannot proceed.", file=sys.stderr)
        sys.exit(1)

    category = "Spinning"
    m_cat = re.search(r'\|\s*種類\s*\|\s*([A-Za-z]+)\s*\|\s*([^|]+)\|', clean_content)
    if m_cat:
        if m_cat.group(1).strip() == "B" or any(k in m_cat.group(2) for k in ["Baitcasting", "兩軸", "槍柄"]):
            category = "Baitcasting"
    elif any(model_name.endswith(sfx) for sfx in ["B", "RB", "FB", "HRB", "MRB", "MHRB", "LRSB"]):
        category = "Baitcasting"

    m_len = re.search(r'\|\s*全長\s*\|\s*([\d\.]+)\s*m', clean_content)
    length_str = f"{float(m_len.group(1))} m" if m_len else "2.10 m"
    m_dia = re.search(r'\|\s*先径[／/]元径\s*\|\s*([\d\.]+)\s*[／/]\s*([\d\.]+)\s*mm', clean_content)
    if m_dia:
        tip_dia_mm, butt_dia_mm = float(m_dia.group(1)), float(m_dia.group(2))
    else:
        print(f"[ERROR] '{os.path.basename(file_path)}' dia info format error.", file=sys.stderr)
        sys.exit(1)
        
    m_ratio = re.search(r'粗細比[（\(]Ratio[）\)]＝\s*([\d\.]+)', clean_content) or re.search(r'Ratio\s*([\d\.]+)', clean_content)
    taper_ratio = float(m_ratio.group(1)) if m_ratio else round(butt_dia_mm / max(0.1, tip_dia_mm), 2)
    
    m_lure = re.search(r'\|\s*ルアー重量[（\(][^|]*[）\)]\s*\|\s*([^|]+)\|', clean_content)
    lure_rating = re.sub(r'\s+', ' ', m_lure.group(1).strip().replace('（', ' (').replace('）', ')')) if m_lure else ""
    if not lure_rating:
        print(f"[ERROR] '{os.path.basename(file_path)}' missing Lure Rating.", file=sys.stderr)
        sys.exit(1)

    m_line = re.search(r'\|\s*適合ライン[（\(][^|]*[）\)]\s*\|\s*([^|]+)\|', clean_content)
    line_rating = re.sub(r'\s+', ' ', m_line.group(1).strip().replace('（', ' (').replace('）', ')')) if m_line else ""

    m_weight = re.search(r'\|\s*標準自重\s*\|\s*([\d\.]+)\s*g', clean_content)
    weight_g = float(m_weight.group(1)) if m_weight else 0.0
    m_closed = re.search(r'\|\s*仕舞寸法\s*\|\s*([\d\.]+)\s*cm', clean_content)
    closed_cm = float(m_closed.group(1)) if m_closed else 0.0

    m_taper = re.search(r'\|\s*調性\s*\|\s*([A-Z\+]+)\s*\|\s*([^|]+)\|', clean_content)
    official_taper = "F" if m_taper and "F" in m_taper.group(1) else "R"
    m_calc_act = re.search(r'物理結構判定[：:]\s*([^\n]+)', clean_content)
    geom_action = m_calc_act.group(1).strip() if m_calc_act else "Regular / Slow"
    
    m_excess = re.search(r'元端過剩指數[^\n]*?\s*([\d\.]+)', clean_content)
    butt_excess = float(m_excess.group(1)) if m_excess else 0.0

    tip_struct = "Solid Tip" if ("MEGA TOP" in raw_content or "-ST" in model_name) else "Tubular"
    initial_flex = 25.0 if tip_struct == "Solid Tip" else (35.0 if official_taper == "F" else 45.0)
    
    max_lure_match = re.search(r'(\d+(?:\.\d+)?)\s*g', lure_rating.split('(')[0])
    max_lure = float(max_lure_match.group(1)) if max_lure_match else 14.0
    
    power_stiffness = 1.2 if max_lure <= 5 else (1.6 if max_lure <= 10 else (2.0 if max_lure <= 18 else 3.0))

    return {
        "model_name": model_name, "category": category,
        "basic_specifications": {
            "Length": length_str, "Tip_Diameter_mm": tip_dia_mm, "Butt_Diameter_mm": butt_dia_mm, 
            "Taper_Ratio": taper_ratio, "Lure_Rating": lure_rating, "Line_Rating": line_rating,
            "Weight_g": weight_g, "Closed_Length_cm": closed_cm
        },
        "taper_action_analysis": {"Official_Taper_Code": official_taper, "Geometry_Calculated_Action": geom_action, "Butt_Excess_Index": butt_excess},
        "material_and_structure_effects": {"Tip_Structure": tip_struct, "Blank_Material": "HVF NANOPLUS", "Anti_Twist_Tech": "X45"},
        "curve_plotting_parameters": {"initial_flex_point_pct": initial_flex, "power_stiffness_factor": power_stiffness, "load_transition_shift_rate": 0.35, "tip_flexibility_multiplier": 1.0, "butt_stiffness_multiplier": 1.0}
    }

def do_extract(input_dir, output_file):
    dataset = []
    md_files = glob.glob(os.path.join(input_dir, "*_分析報告.md"))
    if not md_files:
        print(f"[ERROR] No *_分析報告.md files found in {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    for fp in md_files:
        dataset.append(parse_report_file(fp))
        print(f"  [+] Parsed: {os.path.basename(fp)}")
        
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    print(f"[SUCCESS] Data saved to {output_file}")


# ==========================================
# COMMON PHYSICS & PLOTTING UTILS
# ==========================================
def parse_length_cm(length_str):
    try:
        if "m" in length_str: return float(length_str.split("m")[0].strip()) * 100.0
    except: pass
    return 210.0

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
    length_cm = parse_length_cm(specs.get("Length", "2.10 m"))
    tip_dia, butt_dia = float(specs.get("Tip_Diameter_mm", 1.5)), float(specs.get("Butt_Diameter_mm", 10.0))
    p_flex0 = float(params.get("initial_flex_point_pct", 35.0)) / 100.0
    k_power = float(params.get("power_stiffness_factor", 1.5))
    
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
    match = re.search(r'([\d\.]+)[\s]*[〜～\-]+[\s]*([\d\.]+)[\s]*g', lure_str)
    if match: max_lure = float(match.group(2))
    else:
        g_matches = re.findall(r'([\d\.]+)[\s]*g', lure_str)
        max_lure = float(max([float(x) for x in g_matches])) if g_matches else 14.0
    
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
    fig.suptitle(f"HEARTLAND {category_name} COMPARISON", fontsize=24, color="#333333", fontweight='bold')

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
    taper = rod["taper_action_analysis"].get("Geometry_Calculated_Action", "")
    fig.text(0.87, 0.70, taper, fontsize=12, color="#555555", ha='center', va='center')
    
    lure_str = rod.get("basic_specifications", {}).get("Lure_Rating", "")
    if lure_str: fig.text(0.87, 0.65, f"Lure: {lure_str}", fontsize=12, color="#555555", ha='center', va='center')

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

    baitcasting_rods = [r for r in rod_dataset if r.get("category", "") == "Baitcasting"]
    spinning_rods = [r for r in rod_dataset if r.get("category", "") == "Spinning"]

    os.makedirs(output_dir, exist_ok=True)
    
    plot_zenaq_comparison(baitcasting_rods, "BAITCASTING", 100, output_dir)
    plot_zenaq_comparison(baitcasting_rods, "BAITCASTING", 28, output_dir)
    plot_zenaq_comparison(spinning_rods, "SPINNING", 100, output_dir)
    plot_zenaq_comparison(spinning_rods, "SPINNING", 28, output_dir)

    for rod in rod_dataset:
        lure_str = rod.get("basic_specifications", {}).get("Lure_Rating", "")
        plot_zenaq_progressive(rod, get_dynamic_load_list(lure_str), output_dir)

    print("[SUCCESS] All ZENAQ-style plots generated successfully!")

# ==========================================
# ENGINEERING STYLE PHYSICS & PLOTS
# ==========================================
def calculate_bending_curve_horizontal(rod_data, load_g, num_points=300):
    specs = rod_data["basic_specifications"]
    params = rod_data["curve_plotting_parameters"]
    length_cm = parse_length_cm(specs.get("Length", "2.10 m"))
    tip_dia, butt_dia = float(specs.get("Tip_Diameter_mm", 1.5)), float(specs.get("Butt_Diameter_mm", 10.0))
    p_flex0 = float(params.get("initial_flex_point_pct", 35.0)) / 100.0
    k_power = float(params.get("power_stiffness_factor", 1.5))
    
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
    category = sanitize_text(rod_data.get("category", ""))
    specs = rod_data["basic_specifications"]
    taper_info = rod_data["taper_action_analysis"]
    mat_info = rod_data["material_and_structure_effects"]
    params = rod_data["curve_plotting_parameters"]

    length_cm = parse_length_cm(specs.get("Length", "2.10 m"))
    official_taper = sanitize_text(taper_info.get("Official_Taper_Code", "N/A"))
    calc_action = sanitize_text(taper_info.get("Geometry_Calculated_Action", "N/A"))
    tip_struct = sanitize_text(mat_info.get("Tip_Structure", "Tubular"))

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
    
    title_str = f"DAIWA Heartland {model_name} ({category}) - Load Bending Curves"
    subtitle_str = f"Official Taper: {official_taper} | Tip: {tip_struct} | Calc Action: {calc_action}"
    ax.set_title(f"{title_str}\n{subtitle_str}", fontsize=12, fontweight="bold", pad=12)

    ax.grid(True, linestyle="--", alpha=0.5, color="#bbbbbb")
    ax.set_xlim(-5, length_cm + 10)
    ax.set_ylim(min_y * 1.18, max(10, -min_y * 0.15))

    info_text = (
        f"[Specifications]\n"
        f"- Length: {sanitize_text(specs.get('Length', 'N/A'))}\n"
        f"- Weight: {specs.get('Weight_g', 'N/A')}g | Closed: {specs.get('Closed_Length_cm', 'N/A')}cm\n"
        f"- Tip/Butt Dia: {specs.get('Tip_Diameter_mm', 'N/A')}mm / {specs.get('Butt_Diameter_mm', 'N/A')}mm\n"
        f"- Taper Ratio: {specs.get('Taper_Ratio', 'N/A')} | Butt Excess: {taper_info.get('Butt_Excess_Index', 'N/A')}\n"
        f"- Lure: {sanitize_text(specs.get('Lure_Rating', 'N/A'))}\n"
        f"- Line: {sanitize_text(specs.get('Line_Rating', 'N/A'))}\n\n"
        f"[Model Parameters]\n"
        f"- Initial Flex Point: {params.get('initial_flex_point_pct', 'N/A')}%\n"
        f"- Power Stiffness (Kp): {params.get('power_stiffness_factor', 'N/A')}\n"
        f"- Load Shift Rate (eta): {params.get('load_transition_shift_rate', 'N/A')}\n"
        f"- Tip Mult: {params.get('tip_flexibility_multiplier', 'N/A')} | Butt Mult: {params.get('butt_stiffness_multiplier', 'N/A')}\n\n"
        f"[Tech Features]\n"
        f"- Material: {sanitize_text(mat_info.get('Blank_Material', 'N/A'))}\n"
        f"- Butt Structure: None (3DX Excluded)\n"
        f"- Anti-Twist: {sanitize_text(mat_info.get('Anti_Twist_Tech', 'N/A'))}"
    )

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
