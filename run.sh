#!/usr/bin/env bash
# =============================================================================
# run.sh — MBA Task Scheduling Simulator
# =============================================================================
# Builds and runs the CloudSim Plus MBA simulation, then optionally runs the
# FCFS baseline for comparison.  All output is mirrored to results/run.log.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAVA_DIR="$SCRIPT_DIR/cloudsim-plus-mba"
LOG_FILE="$JAVA_DIR/results/run.log"

# Ensure results directory exists and clear previous log
mkdir -p "$(dirname "$LOG_FILE")"
: > "$LOG_FILE"

separator() {
    echo "=================================================" | tee -a "$LOG_FILE"
}

log() {
    echo "$*" | tee -a "$LOG_FILE"
}

separator
log " MBA Task Scheduling Simulator"
log " Modified Bat Algorithm + CloudSim Plus"
separator
log ""
log " Log file : $LOG_FILE"
log " Project  : $JAVA_DIR"
log " Started  : $(date)"
log ""

# Move into the Maven project directory
cd "$JAVA_DIR" || { echo "[ERROR] Cannot enter $JAVA_DIR"; exit 1; }

# ----------------------------------------------------------------
# Phase 1: MBA simulation
# ----------------------------------------------------------------
separator
log " PHASE 1 — MBA Simulation"
separator

mvn -q compile exec:java -Dexec.args="" 2>&1 | tee -a "$LOG_FILE"
mba_status="${PIPESTATUS[0]}"

if [ "$mba_status" -ne 0 ]; then
    log ""
    log "[ERROR] MBA simulation failed (exit $mba_status)."
    exit "$mba_status"
fi

log ""
log "[OK] MBA simulation completed successfully."

# ----------------------------------------------------------------
# Phase 2: FCFS baseline
# ----------------------------------------------------------------
separator
log " PHASE 2 — FCFS Baseline Simulation"
separator

mvn -q exec:java -Dexec.args="fcfs" 2>&1 | tee -a "$LOG_FILE"
fcfs_status="${PIPESTATUS[0]}"

if [ "$fcfs_status" -ne 0 ]; then
    log ""
    log "[WARN] FCFS baseline failed (exit $fcfs_status). Continuing."
fi

log ""
log "[OK] FCFS baseline completed."

# ----------------------------------------------------------------
# Results and comparison summary
# ----------------------------------------------------------------
separator
log " RESULTS AND COMPARISON"
separator

print_metrics_file() {
    local label="$1"
    local file="$2"

    log ""
    log " $label"
    if [ -f "$file" ]; then
        while IFS= read -r line; do
            log "   $line"
        done < "$file"
    else
        log "   [UNAVAILABLE] $file"
    fi
}

metric_value() {
    local file="$1"
    local key="$2"

    awk -F: -v key="$key" '
        $1 == key {
            value = $2
            sub(/^[[:space:]]+/, "", value)
            match(value, /^[-+]?[0-9]+([.][0-9]+)?/)
            if (RSTART > 0) {
                print substr(value, RSTART, RLENGTH)
            }
            exit
        }
    ' "$file"
}

print_metrics_file "MBA METRICS" "results/metrics.txt"
print_metrics_file "FCFS BASELINE METRICS" "results/fcfs_metrics.txt"

if [ -f "results/metrics.txt" ] && [ -f "results/fcfs_metrics.txt" ]; then
    mba_makespan="$(metric_value results/metrics.txt "Makespan        ")"
    fcfs_makespan="$(metric_value results/fcfs_metrics.txt "Makespan        ")"
    mba_energy="$(metric_value results/metrics.txt "Total Energy    ")"
    fcfs_energy="$(metric_value results/fcfs_metrics.txt "Total Energy    ")"
    mba_util="$(metric_value results/metrics.txt "Avg VM Util.    ")"
    fcfs_util="$(metric_value results/fcfs_metrics.txt "Avg VM Util.    ")"
    mba_throughput="$(metric_value results/metrics.txt "Throughput      ")"
    fcfs_throughput="$(metric_value results/fcfs_metrics.txt "Throughput      ")"

    log ""
    log " COMPARISON (MBA vs FCFS)"
    printf " %-18s %22s %22s %22s\n" \
        "Metric" "MBA" "FCFS" "MBA vs FCFS" | tee -a "$LOG_FILE"
    printf " %-18s %22s %22s %22s\n" \
        "------------------" "----------------------" "----------------------" "----------------------" | tee -a "$LOG_FILE"
    printf " %-18s %22.4f %22.4f %22.2f%%\n" \
        "Makespan (s)" "$mba_makespan" "$fcfs_makespan" \
        "$(awk -v l="$mba_makespan" -v f="$fcfs_makespan" 'BEGIN { if (f == 0) print 0; else print (l - f) / f * 100 }')" | tee -a "$LOG_FILE"
    printf " %-18s %22.4f %22.4f %22.2f%%\n" \
        "Energy (J)" "$mba_energy" "$fcfs_energy" \
        "$(awk -v l="$mba_energy" -v f="$fcfs_energy" 'BEGIN { if (f == 0) print 0; else print (l - f) / f * 100 }')" | tee -a "$LOG_FILE"
    printf " %-18s %22.2f %22.2f %22.2f%%\n" \
        "Avg Utilization" "$mba_util" "$fcfs_util" \
        "$(awk -v l="$mba_util" -v f="$fcfs_util" 'BEGIN { if (f == 0) print 0; else print (l - f) / f * 100 }')" | tee -a "$LOG_FILE"
    printf " %-18s %22.6f %22.6f %22.2f%%\n" \
        "Throughput" "$mba_throughput" "$fcfs_throughput" \
        "$(awk -v l="$mba_throughput" -v f="$fcfs_throughput" 'BEGIN { if (f == 0) print 0; else print (l - f) / f * 100 }')" | tee -a "$LOG_FILE"
    log ""
    log " Persentase negatif pada makespan/energi berarti MBA lebih baik dari FCFS."
fi

separator
log " RUN COMPLETE"
separator
log " Finished : $(date)"
log ""
log " Output files:"
log "   - results/run.log          (this log)"
log "   - results/mba_mapping.csv (task→VM mapping)"
log "   - results/metrics.txt      (MBA performance metrics)"
log "   - results/fcfs_metrics.txt (FCFS baseline metrics)"
separator
