import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data_path = root / "outputs/kaggle_results/v31-ar-oracle-run3/outputs/v31-ar-oracle-run3/run_state.json"
runtime_path = root / "outputs/kaggle_results/v31-ar-oracle-run3/outputs/v31-ar-oracle-run3/runtime.json"

if not data_path.exists():
    print("Results file not found at", data_path)
    exit(1)

data = json.loads(data_path.read_text(encoding="utf-8"))
runtime = json.loads(runtime_path.read_text(encoding="utf-8")) if runtime_path.exists() else {}

print("================================================================")
print("             V31 ACTION RECOGNITION ORACLE RUN REPORT          ")
print("================================================================")
print(f"Device:           {runtime.get('gpu', 'Tesla T4')}")
print(f"Git Commit:       {runtime.get('commit', '9abbb9b')}")
print(f"Overall Status:   {data.get('stages', {}).get('oracle', {}).get('status', 'UNKNOWN')}")
print(f"Counts:           {data.get('stages', {}).get('oracle', {}).get('counts', {})}")

oracle = data.get("stages", {}).get("oracle", {})
arms = oracle.get("arms", {})

for arm in ("a", "b", "c"):
    arm_data = arms.get(arm, {})
    arm_st = arm_data.get("status")
    print(f"\n------------------------- ARM {arm.upper()} [{arm_st}] -------------------------")
    codecs = arm_data.get("headroom", {}).get("codecs", {})
    for c in ("h264", "h265"):
        c_info = codecs.get(c, {})
        anc = c_info.get("anchor", {})
        print(f"  * Codec {c.upper()}:")
        print(f"    - Passed:        {c_info.get('passed')}")
        print(f"    - Reasons:       {c_info.get('reasons')}")
        print(f"    - Cubic BD-rate: {anc.get('cubic_bd_rate_pct', 0.0):.2f}%")
        print(f"    - PCHIP BD-rate: {anc.get('pchip_bd_rate_pct', 0.0):.2f}%")
        same_r = [round(x, 2) for x in anc.get("same_qp_rate_pct", [])]
        same_q = [round(x, 2) for x in anc.get("same_qp_quality_gap_pp", [])]
        print(f"    - Rate Delta %:  {same_r}")
        print(f"    - Quality Gap pp:{same_q}")

print("\n================================================================")
