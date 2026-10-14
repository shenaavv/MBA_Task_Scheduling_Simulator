#!/usr/bin/env python3
"""Convert 100 task records from the official Google Cluster Trace v1."""

import csv
import gzip
import math
from pathlib import Path


DATASET_DIR = Path(__file__).resolve().parent
SOURCE = DATASET_DIR / "google-cluster-data-1.csv.gz"
OUTPUT = DATASET_DIR / "tasks.csv"
TASK_LIMIT = 100


def convert_row(row, task_id):
    normalized_cores = float(row["NrmlTaskCores"])
    normalized_memory = float(row["NrmlTaskMem"])

    # The v1 trace exposes normalized demand, not MI or absolute RAM.
    pes = max(1, min(4, math.ceil(normalized_cores * 32)))
    length_mi = max(1, round(normalized_cores * 1_000_000))
    ram_mb = max(1024, round(normalized_memory * 64 * 1024))

    return {
        "taskId": task_id,
        "lengthMI": length_mi,
        "pes": pes,
        "ramMB": ram_mb,
        "priority": int(row["JobType"]),
    }


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Raw trace not found: {SOURCE}\n"
            "Download from: "
            "http://commondatastorage.googleapis.com/clusterdata-misc/google-cluster-data-1.csv.gz"
        )

    fieldnames = ["Time", "ParentID", "TaskID", "JobType", "NrmlTaskCores", "NrmlTaskMem"]
    seen_task_ids = set()
    rows = []

    with gzip.open(SOURCE, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f, fieldnames=fieldnames)
        for raw_row in reader:
            try:
                cores = float(raw_row["NrmlTaskCores"])
            except ValueError:
                continue
            if cores <= 0:
                continue
            tid = raw_row["TaskID"]
            if tid in seen_task_ids:
                continue
            seen_task_ids.add(tid)
            rows.append(convert_row(raw_row, len(rows) + 1))
            if len(rows) >= TASK_LIMIT:
                break

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["taskId", "lengthMI", "pes", "ramMB", "priority"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Written {len(rows)} tasks to {OUTPUT}")


if __name__ == "__main__":
    main()
