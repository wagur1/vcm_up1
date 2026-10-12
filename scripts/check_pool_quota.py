"""Check quota and active status for all Kaggle accounts in a pool JSON file."""
import json
import os
import subprocess
import sys
from pathlib import Path


def check_pool(pool_path: str):
    p = Path(pool_path)
    if not p.is_file():
        print(f"File not found: {pool_path}")
        return

    pool_data = json.loads(p.read_text(encoding="utf-8-sig"))
    print(f"Loaded {len(pool_data)} accounts from {pool_path}\n")

    results = []
    for idx, (username, token) in enumerate(pool_data.items(), 1):
        print(f"[{idx:>2}/{len(pool_data)}] Checking account: {username:<20} ...", end=" ", flush=True)

        env = dict(os.environ)
        for k in ("KAGGLE_API_TOKEN", "KAGGLE_USERNAME", "KAGGLE_KEY"):
            env.pop(k, None)

        if isinstance(token, str):
            env["KAGGLE_API_TOKEN"] = token
        elif isinstance(token, dict) and "key" in token:
            env["KAGGLE_USERNAME"] = token.get("username", username)
            env["KAGGLE_KEY"] = token["key"]

        account_info = {
            "account": username,
            "status": "OK",
            "gpu_used": "N/A",
            "gpu_remaining": "N/A",
            "gpu_total": "N/A",
            "tpu_remaining": "N/A",
            "refresh_at": "",
            "active_kernels": [],
            "error": None
        }

        try:
            # Query quota via kaggle CLI
            res = subprocess.run(
                [sys.executable, "-m", "kaggle", "quota", "--format", "json"],
                env=env, capture_output=True, text=True, timeout=20
            )
            if res.returncode != 0:
                raise RuntimeError(res.stderr.strip() or f"Exit {res.returncode}")

            quota_list = json.loads(res.stdout)
            for item in quota_list:
                if item.get("resource") == "GPU":
                    account_info["gpu_used"] = item.get("used", "0h")
                    account_info["gpu_remaining"] = item.get("remaining", "0h")
                    account_info["gpu_total"] = item.get("total", "0h")
                    account_info["refresh_at"] = item.get("refreshAt", "")
                elif item.get("resource") == "TPU":
                    account_info["tpu_remaining"] = item.get("remaining", "0h")

            # Check recent active kernels
            k_res = subprocess.run(
                [sys.executable, "-m", "kaggle", "kernels", "list", "--mine", "--page-size", "5", "--format", "json"],
                env=env, capture_output=True, text=True, timeout=20
            )
            if k_res.returncode == 0:
                try:
                    kernels = json.loads(k_res.stdout)
                    # Check status of the most recent kernel if available
                    if kernels:
                        first_ref = kernels[0].get("ref")
                        if first_ref:
                            st_res = subprocess.run(
                                [sys.executable, "-m", "kaggle", "kernels", "status", first_ref],
                                env=env, capture_output=True, text=True, timeout=15
                            )
                            if st_res.returncode == 0:
                                st_text = st_res.stdout.strip()
                                if any(x in st_text for x in ("RUNNING", "QUEUED")):
                                    account_info["active_kernels"].append(f"{first_ref} ({st_text})")
                except Exception:
                    pass

            print(f"OK | GPU: {account_info['gpu_remaining']:>6} avail / {account_info['gpu_total']:>6} (Used: {account_info['gpu_used']})")
        except Exception as e:
            account_info["status"] = "ERROR"
            account_info["error"] = str(e)
            print(f"FAILED: {e}")

        results.append(account_info)

    print("\n" + "="*85)
    print(f"{'Account':<20} | {'Status':<6} | {'GPU Rem':<8} | {'GPU Used':<8} | {'GPU Total':<9} | {'Refresh At':<19} | {'Active'}")
    print("="*85)
    for r in results:
        active_str = ", ".join(r["active_kernels"]) if r["active_kernels"] else "-"
        print(f"{r['account']:<20} | {r['status']:<6} | {r['gpu_remaining']:<8} | {r['gpu_used']:<8} | {r['gpu_total']:<9} | {r['refresh_at']:<19} | {active_str}")
    print("="*85)

    summary_path = p.parent / "pool_quota_summary.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved summary to: {summary_path}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Wagur1\Downloads\pool (1).json"
    check_pool(target)
