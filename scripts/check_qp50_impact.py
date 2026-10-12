import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json
from adaptive_vcm.legacy_bd import bd_rate
from adaptive_vcm.metrics import pchip_bd

with open(ROOT / "docs/results/v22_audit.json", "r", encoding="utf-8") as f:
    data = json.load(f)

qps = [30, 35, 40, 45, 50]

for task_name in ["ar", "od"]:
    task_res = data["tasks"][task_name]["results"]
    print("\n" + "="*70)
    print(f"=== TASK: {task_name.upper()} ===")
    print("="*70)
    for run_name, run_data in task_res.items():
        anchor_bpp = run_data["curves"]["anchor"]["bpp"]
        anchor_q = run_data["curves"]["anchor"]["quality"]
        adap_bpp = run_data["curves"]["adaptive"]["bpp"]
        adap_q = run_data["curves"]["adaptive"]["quality"]
        
        full_bd = run_data["bd_rate_pct"]
        full_pchip = run_data["pchip_bd_rate_pct"]
        
        # Calculate without QP 50 (first 4 points: QP 30, 35, 40, 45)
        bd_no50 = bd_rate(anchor_bpp[:4], anchor_q[:4], adap_bpp[:4], adap_q[:4])
        pchip_no50 = pchip_bd(anchor_bpp[:4], anchor_q[:4], adap_bpp[:4], adap_q[:4])
        
        print(f"\n* Run: {run_name}")
        print(f"  [FULL 5-QP: 30, 35, 40, 45, 50] : BD-rate = {full_bd:+.2f}% | PCHIP = {full_pchip:+.2f}%")
        print(f"  [NO QP 50 -> ONLY QP 30..45]    : BD-rate = {bd_no50:+.2f}% | PCHIP = {pchip_no50:+.2f}%")
        
        print("  Detail per QP:")
        for i, qp in enumerate(qps):
            diff_rate = ((adap_bpp[i] - anchor_bpp[i]) / anchor_bpp[i]) * 100
            diff_q = (adap_q[i] - anchor_q[i]) * 100
            print(f"    - QP {qp:2d}: Rate Diff = {diff_rate:+6.2f}% | Delta Quality = {diff_q:+6.2f} pp (Raw: {anchor_q[i]*100:5.2f}%, Pre: {adap_q[i]*100:5.2f}%)")
