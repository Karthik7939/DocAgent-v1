"""
scripts/compute_validation_stats.py
--------------------------------------
Computes the Self-Correction Pass-Rate Stats (docagent_evaluation_plan.md,
Section 1) from eval_logs/validation_log.csv, written by
agents.coordinator.validation_log.log_validation_event() as the pipeline
runs.

Usage:
    python scripts/compute_validation_stats.py [path/to/validation_log.csv]

If no path is given, defaults to eval_logs/validation_log.csv relative to
the backend root.
"""

import os
import sys

import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
DEFAULT_LOG_PATH = os.path.join(_BACKEND_ROOT, "eval_logs", "validation_log.csv")


def main() -> int:
    log_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG_PATH
    if not os.path.exists(log_path):
        print(f"No validation log found at {log_path}. Run the pipeline first.", file=sys.stderr)
        return 1

    df = pd.read_csv(log_path)
    if df.empty:
        print("Validation log is empty — no runs recorded yet.", file=sys.stderr)
        return 1

    # First-pass pass rate (cycle 0), split into strict (sync only) vs any-pass
    first_pass = df[df.cycle == 0]
    first_pass_rate = (first_pass.routed_to == "sync").mean()

    # Final outcome per doc_id (last row per doc_id across cycles)
    final_rows = df.sort_values("cycle").groupby("doc_id").tail(1)
    final_pass_rate = (final_rows.routed_to == "sync").mean()
    failed_rate = (final_rows.routed_to == "failed").mean()

    # Mean score by cycle number (shows improvement trend across revisions)
    mean_score_by_cycle = df.groupby("cycle").score.mean()

    # Average cycles to convergence, for docs that eventually passed
    passed_docs = final_rows[final_rows.routed_to == "sync"].doc_id
    avg_cycles = (
        df[df.doc_id.isin(passed_docs)].groupby("doc_id").cycle.max().mean()
        if len(passed_docs) else float("nan")
    )

    n_docs = df.doc_id.nunique()

    print(f"Runs analysed: {n_docs} unique doc_id(s), {len(df)} validation events\n")
    print(f"{'Metric':<45}{'Value'}")
    print("-" * 60)
    print(f"{'First-pass pass rate (cycle 0, sync only)':<45}{first_pass_rate:.1%}")
    print(f"{'Final pass rate (within max revisions)':<45}{final_pass_rate:.1%}")
    print(f"{'FAILED rate (exhausted revisions)':<45}{failed_rate:.1%}")
    print(f"{'Avg. cycles to convergence (passed docs)':<45}{avg_cycles:.2f}")
    print()
    print("Mean score by cycle:")
    print(mean_score_by_cycle.to_string())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
