"""Monitor V31 primary job and orchestrate sharding/merge/eval pipeline automatically."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = r"C:\Users\Wagur1\Downloads\pool (1).json"
REGISTRY_PATH = ROOT / "outputs/adaptive_v31_jobs/run_registry.json"


def call_registry(argv: list[str]) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    cmd = [sys.executable, str(ROOT / "scripts/run_v31_jobs.py"), *argv,
           "--registry", str(REGISTRY_PATH), "--pool", POOL_PATH]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        raise RuntimeError(f"run_v31_jobs failed ({res.returncode}): {res.stderr}\n{res.stdout}")
    return json.loads(res.stdout)


def monitor_job(job_id: str, interval: int = 30, max_wait_minutes: int = 600) -> dict:
    start_time = time.time()
    last_status = None
    print(f"Monitoring job: {job_id}")
    while True:
        elapsed_m = (time.time() - start_time) / 60.0
        if elapsed_m > max_wait_minutes:
            print(f"Timeout exceeded ({max_wait_minutes} minutes)")
            break

        try:
            status_data = call_registry(["status", "--job", job_id])
            st = status_data.get("status")
            stages = status_data.get("stages") or {}
            runtime = status_data.get("runtime") or {}

            if st != last_status or stages:
                print(f"[{time.strftime('%H:%M:%S')}] Status: {st} | Elapsed: {elapsed_m:.1f}m | GPU: {runtime.get('gpu', 'N/A')}")
                if stages:
                    for stage_name, stage_res in stages.items():
                        print(f"   -> Stage '{stage_name}': {stage_res.get('status', 'RUNNING')}")
                last_status = st

            if st in ("COMPLETE", "ERROR", "CANCELLED", "CANCEL_ACKNOWLEDGED"):
                print(f"\nJob reached terminal state: {st}")
                return status_data

        except Exception as e:
            print(f"Status check error: {e}")

        time.sleep(interval)

    return {}


if __name__ == "__main__":
    job_target = sys.argv[1] if len(sys.argv) > 1 else "nguyenhoanglan1232/v31-ar-oracle-run1"
    monitor_job(job_target)
