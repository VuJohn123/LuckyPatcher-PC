"""
End-to-end test với APK thật.
Chạy: python scripts/e2e_test.py <path-to-apk>
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# Add src/ vào path
_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E test pipeline")
    parser.add_argument("apk", help="APK / XAPK / APKS path")
    parser.add_argument(
        "--mode", default="license:auto,iap:dex",
        help="Modes để test (comma-separated)"
    )
    parser.add_argument("--keep-workspace", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.apk):
        print(f"[!] File không tồn tại: {args.apk}")
        return 1

    print("=" * 70)
    print("E2E Test — LP-PC Suite")
    print("=" * 70)
    print(f"Input:  {args.apk}")
    print(f"Mode:   {args.mode}")
    print("=" * 70)

    from core.config import load_config
    from main import run_pipeline

    t0 = time.monotonic()
    success, out, reports = run_pipeline(
        args.apk,
        mode=args.mode,
        log_callback=lambda msg: print(msg, flush=True),
        fast_mode=True,
        use_gda=False,
        keep_workspace=args.keep_workspace,
        config=load_config(),
    )
    elapsed = time.monotonic() - t0

    print("=" * 70)
    if success:
        print(f"✅ SUCCESS in {elapsed:.1f}s")
        print(f"Output: {out}")
        size_mb = os.path.getsize(out) / 1024 / 1024 if out else 0
        print(f"Size:   {size_mb:.1f} MB")
        print(f"Reports: {reports}")
        return 0
    else:
        print(f"❌ FAILED in {elapsed:.1f}s")
        return 1


if __name__ == "__main__":
    sys.exit(main())