#!/usr/bin/env python3
"""
Scalability Experiment: MBA vs FCFS — Task Count 100–1000
==========================================================

Reimplements the MBA and FCFS scheduling algorithms using the same cloud
architecture parameters as the Java/CloudSim Plus simulator.  Generates
datasets of varying sizes (100-1000 tasks) by resampling the original
Google Cluster Trace dataset, runs both algorithms, collects performance
metrics, and produces comparison graphs.

Cloud Architecture (identical to MBACloudTaskScheduling.java):
  - 1 Datacenter, 4 Hosts, 8 VMs
  - VM0-VM1: 2 PE, 1000 MIPS/PE   (Host 0)
  - VM2-VM3: 4 PE, 1500 MIPS/PE   (Host 1)
  - VM4-VM5: 4 PE, 2000 MIPS/PE   (Host 2)
  - VM6-VM7: 8 PE, 2500 MIPS/PE   (Host 3)

Energy Model:
  - VM0-VM1: idle 50W,  busy 150W
  - VM2-VM3: idle 75W,  busy 220W
  - VM4-VM5: idle 100W, busy 300W
  - VM6-VM7: idle 150W, busy 450W

Author: Kelompok 4 — SOKA (A)
"""

import csv
import math
import os
import random
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# ---------------------------------------------------------------------------
# Cloud architecture parameters (matching Java source exactly)
# ---------------------------------------------------------------------------
VM_PES      = [2, 2, 4, 4, 4, 4, 8, 8]
VM_MIPS     = [1000, 1000, 1500, 1500, 2000, 2000, 2500, 2500]
VM_POWER_IDLE = [50, 50, 75, 75, 100, 100, 150, 150]   # Watts
VM_POWER_BUSY = [150, 150, 220, 220, 300, 300, 450, 450]  # Watts
NUM_VMS = len(VM_MIPS)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Task:
    """Lightweight task descriptor mirroring TaskData in Java."""
    __slots__ = ("task_id", "length_mi", "pes", "ram_mb", "priority")

    def __init__(self, task_id: int, length_mi: int, pes: int,
                 ram_mb: int, priority: int):
        self.task_id   = task_id
        self.length_mi = length_mi
        self.pes       = pes
        self.ram_mb    = ram_mb
        self.priority  = priority

# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------

def load_base_tasks(csv_path: str) -> list[Task]:
    """Read the original 100-task CSV."""
    tasks = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tasks.append(Task(
                task_id   = int(row["taskId"]),
                length_mi = int(row["lengthMI"]),
                pes       = int(row["pes"]),
                ram_mb    = int(row["ramMB"]),
                priority  = int(row["priority"]),
            ))
    return tasks


def generate_dataset(base_tasks: list[Task], n: int,
                     seed: int = 42) -> list[Task]:
    """
    Generate a dataset of *n* tasks by sampling with replacement from
    *base_tasks*.  A fixed seed ensures reproducibility.
    """
    rng = random.Random(seed)
    tasks = []
    for i in range(n):
        src = rng.choice(base_tasks)
        tasks.append(Task(
            task_id   = i + 1,
            length_mi = src.length_mi,
            pes       = src.pes,
            ram_mb    = src.ram_mb,
            priority  = src.priority,
        ))
    return tasks

# ---------------------------------------------------------------------------
# Scheduling algorithms
# ---------------------------------------------------------------------------

def mba_schedule(tasks: list[Task]) -> list[int]:
    """
    Modified Bat Algorithm using integer VM assignments as bat positions.

    A deterministic seed makes the scalability experiment reproducible. Each
    candidate is kept when its estimated makespan plus a small energy penalty
    improves, while loudness and frequency balance exploration/exploitation.
    """
    rng = random.Random(42)

    def feasible_vm(task: Task) -> int:
        choices = [j for j in range(NUM_VMS) if VM_PES[j] >= task.pes]
        return rng.choice(choices) if choices else rng.randrange(NUM_VMS)

    def score(mapping: list[int]) -> float:
        loads = [0.0] * NUM_VMS
        for task, vm in zip(tasks, mapping):
            loads[vm] += task.length_mi / VM_MIPS[vm]
        return max(loads, default=0.0) + sum(
            loads[j] * VM_POWER_BUSY[j] for j in range(NUM_VMS)
        ) / 1_000_000.0

    population = [[feasible_vm(task) for task in tasks] for _ in range(16)]
    scores = [score(position) for position in population]
    best = population[min(range(len(population)), key=scores.__getitem__)].copy()
    best_score = score(best)
    loudness = 1.0

    for _ in range(80):
        frequency = 0.1 + 0.9 * rng.random()
        for bat, current_score in enumerate(scores):
            candidate = population[bat].copy()
            for i, task in enumerate(tasks):
                if rng.random() < loudness * frequency:
                    candidate[i] = best[i]
                elif rng.random() < 0.08:
                    candidate[i] = feasible_vm(task)
            if rng.random() < loudness:
                i = rng.randrange(len(tasks))
                candidate[i] = feasible_vm(tasks[i])
            candidate_score = score(candidate)
            if candidate_score < current_score:
                population[bat] = candidate
                scores[bat] = candidate_score
                if candidate_score < best_score:
                    best, best_score = candidate.copy(), candidate_score
        loudness *= 0.97

    return tasks, best


def fcfs_schedule(tasks: list[Task]) -> list[int]:
    """
    First-Come First-Served with Round-Robin VM assignment
    (mirrors DatacenterBrokerSimple default behaviour).

    Tasks keep their original order; each task goes to the next VM
    in a cyclic fashion.
    """
    mapping = [i % NUM_VMS for i in range(len(tasks))]
    return tasks, mapping

# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(tasks: list[Task], mapping: list[int]) -> dict:
    """
    Compute makespan, energy, avg utilisation, and throughput.

    Model: each VM processes assigned tasks.  A VM with P PEs can run
    P tasks (each needing 1 PE) concurrently.  We batch tasks in groups
    of P and process batches sequentially; each batch finishes when the
    longest task in it completes.  This closely approximates CloudSim's
    TimeShared behaviour for pes=1 tasks on multi-PE VMs.
    """
    n = len(tasks)

    # Group tasks per VM
    vm_tasks: list[list[Task]] = [[] for _ in range(NUM_VMS)]
    for i, vm_idx in enumerate(mapping):
        vm_tasks[vm_idx].append(tasks[i])

    # Per-VM makespan with parallel PE execution
    vm_makespan = [0.0] * NUM_VMS
    vm_busy     = [0.0] * NUM_VMS   # total busy-seconds across all PEs

    for j in range(NUM_VMS):
        tlist = vm_tasks[j]
        if not tlist:
            continue

        pes = VM_PES[j]
        mips = VM_MIPS[j]

        # Sort tasks descending within VM for bin-packing into PE-batches
        exec_times = sorted(
            [t.length_mi / mips for t in tlist], reverse=True
        )

        # Assign tasks to PE "lanes" using least-loaded strategy
        pe_lanes = [0.0] * pes
        for et in exec_times:
            # Find PE lane with smallest load
            min_lane = min(range(pes), key=lambda p: pe_lanes[p])
            pe_lanes[min_lane] += et

        vm_makespan[j] = max(pe_lanes)
        vm_busy[j]     = sum(pe_lanes)  # total PE-seconds busy

    makespan = max(vm_makespan) if any(vm_makespan) else 0.0

    # Energy
    total_energy = 0.0
    for j in range(NUM_VMS):
        busy_t = vm_makespan[j]
        idle_t = max(0.0, makespan - busy_t)
        total_energy += busy_t * VM_POWER_BUSY[j] + idle_t * VM_POWER_IDLE[j]

    # Average VM utilisation
    if makespan > 0:
        utils = [min(vm_makespan[j], makespan) / makespan for j in range(NUM_VMS)]
        avg_util = (sum(utils) / NUM_VMS) * 100.0
    else:
        avg_util = 0.0

    # Throughput
    throughput = n / makespan if makespan > 0 else 0.0

    return {
        "tasks_completed": n,
        "makespan":        makespan,
        "energy":          total_energy,
        "avg_util":        avg_util,
        "throughput":      throughput,
    }

# ---------------------------------------------------------------------------
# Graph generation
# ---------------------------------------------------------------------------

def create_graphs(task_counts, mba_results, fcfs_results, output_dir):
    """Create beautiful comparison graphs."""

    # Set up style
    plt.rcParams.update({
        "figure.facecolor":   "#0f0f1a",
        "axes.facecolor":     "#1a1a2e",
        "axes.edgecolor":     "#333355",
        "axes.labelcolor":    "#e0e0e0",
        "text.color":         "#e0e0e0",
        "xtick.color":        "#b0b0b0",
        "ytick.color":        "#b0b0b0",
        "grid.color":         "#2a2a4a",
        "grid.alpha":         0.6,
        "font.family":        "sans-serif",
        "font.size":          11,
        "legend.facecolor":   "#1a1a2e",
        "legend.edgecolor":   "#444466",
        "legend.fontsize":    10,
    })

    mba_color = "#00d4ff"   # cyan
    fcfs_color = "#ff6b6b"   # coral red
    mba_fill  = "#00d4ff20"
    fcfs_fill  = "#ff6b6b20"

    metrics = [
        ("makespan",   "Makespan (detik)",          "Makespan vs Jumlah Task"),
        ("energy",     "Total Energi (Joule)",       "Konsumsi Energi vs Jumlah Task"),
        ("avg_util",   "Rata-rata Utilisasi VM (%)", "Utilisasi VM vs Jumlah Task"),
        ("throughput", "Throughput (task/detik)",     "Throughput vs Jumlah Task"),
    ]

    # Individual graphs
    for key, ylabel, title in metrics:
        fig, ax = plt.subplots(figsize=(10, 6))

        mba_vals = [r[key] for r in mba_results]
        fcfs_vals = [r[key] for r in fcfs_results]

        ax.plot(task_counts, mba_vals, "o-", color=mba_color, linewidth=2.5,
                markersize=8, label="MBA", zorder=5)
        ax.plot(task_counts, fcfs_vals, "s--", color=fcfs_color, linewidth=2.5,
                markersize=8, label="FCFS", zorder=5)

        ax.fill_between(task_counts, mba_vals, alpha=0.12, color=mba_color)
        ax.fill_between(task_counts, fcfs_vals, alpha=0.08, color=fcfs_color)

        ax.set_xlabel("Jumlah Task", fontsize=13, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=13, fontweight="bold")
        ax.set_title(title, fontsize=16, fontweight="bold", pad=15)
        ax.legend(loc="best", framealpha=0.9)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.set_xticks(task_counts)

        # Add subtle glow effect
        for spine in ax.spines.values():
            spine.set_linewidth(0.5)

        fig.tight_layout()
        fname = os.path.join(output_dir, f"graph_{key}.png")
        fig.savefig(fname, dpi=180, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        print(f"  [SAVED] {fname}")

    # Combined 2x2 figure
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(
        "MBA vs FCFS — Scalability Analysis (100–1000 Tasks)",
        fontsize=18, fontweight="bold", y=0.98, color="#ffffff"
    )

    for idx, (key, ylabel, title) in enumerate(metrics):
        ax = axes[idx // 2][idx % 2]

        mba_vals = [r[key] for r in mba_results]
        fcfs_vals = [r[key] for r in fcfs_results]

        ax.plot(task_counts, mba_vals, "o-", color=mba_color, linewidth=2.2,
                markersize=7, label="MBA", zorder=5)
        ax.plot(task_counts, fcfs_vals, "s--", color=fcfs_color, linewidth=2.2,
                markersize=7, label="FCFS", zorder=5)

        ax.fill_between(task_counts, mba_vals, alpha=0.12, color=mba_color)
        ax.fill_between(task_counts, fcfs_vals, alpha=0.08, color=fcfs_color)

        ax.set_xlabel("Jumlah Task", fontsize=11, fontweight="bold")
        ax.set_ylabel(ylabel, fontsize=11, fontweight="bold")
        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
        ax.legend(loc="best", framealpha=0.9)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.set_xticks(task_counts)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fname = os.path.join(output_dir, "graph_combined.png")
    fig.savefig(fname, dpi=180, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  [SAVED] {fname}")

    # Improvement percentage graph
    fig, ax = plt.subplots(figsize=(10, 6))

    improvement_metrics = [
        ("makespan",   "Makespan",    "#00d4ff"),
        ("energy",     "Energi",      "#ffd700"),
        ("throughput", "Throughput",   "#00ff88"),
    ]

    bar_width = 25
    x_pos = np.array(task_counts)

    for i, (key, label, color) in enumerate(improvement_metrics):
        improvements = []
        for j in range(len(task_counts)):
            fcfs_val = fcfs_results[j][key]
            mba_val = mba_results[j][key]
            if fcfs_val != 0:
                if key in ("makespan", "energy"):
                    # Reduction is good → show as positive improvement
                    pct = ((fcfs_val - mba_val) / fcfs_val) * 100
                else:
                    # Increase is good
                    pct = ((mba_val - fcfs_val) / fcfs_val) * 100
            else:
                pct = 0
            improvements.append(pct)

        offset = (i - 1) * bar_width
        bars = ax.bar(x_pos + offset, improvements, width=bar_width - 2,
                      color=color, alpha=0.85, label=f"{label}", zorder=3)

        # Add value labels on bars
        for bar, val in zip(bars, improvements):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f"{val:.1f}%", ha="center", va="bottom", fontsize=7,
                    color=color, fontweight="bold")

    ax.set_xlabel("Jumlah Task", fontsize=13, fontweight="bold")
    ax.set_ylabel("Improvement MBA vs FCFS (%)", fontsize=13, fontweight="bold")
    ax.set_title("Persentase Peningkatan MBA dibanding FCFS",
                 fontsize=16, fontweight="bold", pad=15)
    ax.legend(loc="best", framealpha=0.9)
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    ax.set_xticks(task_counts)
    ax.axhline(y=0, color="#666688", linewidth=0.8)

    fig.tight_layout()
    fname = os.path.join(output_dir, "graph_improvement.png")
    fig.savefig(fname, dpi=180, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  [SAVED] {fname}")

# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def save_results_csv(task_counts, mba_results, fcfs_results, output_dir):
    """Save all metrics to a CSV for reference."""
    fname = os.path.join(output_dir, "scalability_results.csv")
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "TaskCount",
            "MBA_Makespan_s", "FCFS_Makespan_s",
            "MBA_Energy_J",   "FCFS_Energy_J",
            "MBA_AvgUtil_%",  "FCFS_AvgUtil_%",
            "MBA_Throughput",  "FCFS_Throughput",
        ])
        for i, n in enumerate(task_counts):
            lr = mba_results[i]
            fr = fcfs_results[i]
            writer.writerow([
                n,
                f"{lr['makespan']:.4f}",  f"{fr['makespan']:.4f}",
                f"{lr['energy']:.4f}",    f"{fr['energy']:.4f}",
                f"{lr['avg_util']:.2f}",  f"{fr['avg_util']:.2f}",
                f"{lr['throughput']:.6f}", f"{fr['throughput']:.6f}",
            ])
    print(f"  [SAVED] {fname}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    script_dir  = Path(__file__).resolve().parent
    dataset_csv = script_dir / "cloudsim-plus-mba" / "dataset" / "tasks.csv"
    output_dir  = script_dir / "cloudsim-plus-mba" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 60)
    print(" MBA vs FCFS — Scalability Experiment")
    print(" Task counts: 100, 200, 300, ..., 1000")
    print("=" * 60)
    print()

    # 1. Load base dataset
    print("[1] Loading base dataset ...")
    base_tasks = load_base_tasks(str(dataset_csv))
    print(f"    Base dataset: {len(base_tasks)} tasks loaded from {dataset_csv.name}")
    print()

    # 2. Run experiments
    task_counts  = list(range(100, 1001, 100))  # 100, 200, ..., 1000
    mba_results = []
    fcfs_results = []

    print("[2] Running simulations ...")
    print(f"    {'Tasks':>6}  {'MBA Makespan':>14}  {'FCFS Makespan':>14}  "
          f"{'MBA Energy':>14}  {'FCFS Energy':>14}  "
          f"{'MBA Util%':>10}  {'FCFS Util%':>10}")
    print("    " + "-" * 96)

    for n in task_counts:
        # Generate dataset
        dataset = generate_dataset(base_tasks, n, seed=42)

        # Run MBA
        sorted_tasks, mba_map = mba_schedule(dataset)
        mba_m = compute_metrics(sorted_tasks, mba_map)
        mba_results.append(mba_m)

        # Run FCFS
        fcfs_tasks, fcfs_map = fcfs_schedule(dataset)
        fcfs_m = compute_metrics(fcfs_tasks, fcfs_map)
        fcfs_results.append(fcfs_m)

        print(f"    {n:>6}  {mba_m['makespan']:>14.4f}  {fcfs_m['makespan']:>14.4f}  "
              f"{mba_m['energy']:>14.4f}  {fcfs_m['energy']:>14.4f}  "
              f"{mba_m['avg_util']:>10.2f}  {fcfs_m['avg_util']:>10.2f}")

    print()

    # 3. Save CSV results
    print("[3] Saving results ...")
    save_results_csv(task_counts, mba_results, fcfs_results, str(output_dir))

    # 4. Generate graphs
    print()
    print("[4] Generating graphs ...")
    create_graphs(task_counts, mba_results, fcfs_results, str(output_dir))

    # 5. Summary
    print()
    print("=" * 60)
    print(" EXPERIMENT COMPLETE")
    print("=" * 60)
    print()
    print(" Output files:")
    print(f"   - {output_dir / 'scalability_results.csv'}")
    print(f"   - {output_dir / 'graph_makespan.png'}")
    print(f"   - {output_dir / 'graph_energy.png'}")
    print(f"   - {output_dir / 'graph_avg_util.png'}")
    print(f"   - {output_dir / 'graph_throughput.png'}")
    print(f"   - {output_dir / 'graph_combined.png'}")
    print(f"   - {output_dir / 'graph_improvement.png'}")
    print()

    # Print final comparison table
    print(" FINAL COMPARISON TABLE")
    print(" " + "-" * 90)
    print(f" {'Tasks':>6} | {'Makespan Reduction':>18} | {'Energy Reduction':>16} | "
          f"{'Util Improvement':>16} | {'Throughput Gain':>15}")
    print(" " + "-" * 90)

    for i, n in enumerate(task_counts):
        lr = mba_results[i]
        fr = fcfs_results[i]

        ms_red  = ((fr["makespan"] - lr["makespan"]) / fr["makespan"] * 100
                    if fr["makespan"] else 0)
        en_red  = ((fr["energy"] - lr["energy"]) / fr["energy"] * 100
                    if fr["energy"] else 0)
        ut_imp  = lr["avg_util"] - fr["avg_util"]
        tp_gain = ((lr["throughput"] - fr["throughput"]) / fr["throughput"] * 100
                    if fr["throughput"] else 0)

        print(f" {n:>6} | {ms_red:>17.2f}% | {en_red:>15.2f}% | "
              f"{ut_imp:>+15.2f}pp | {tp_gain:>14.2f}%")

    print(" " + "-" * 90)
    print()


if __name__ == "__main__":
    main()
