#!/usr/bin/env python3
"""Summarize the complete four-cell study without discarding failed runs."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import statistics


def describe(values):
    return {"n": len(values), "mean": statistics.mean(values), "median": statistics.median(values),
            "min": min(values), "max": max(values), "sampleStdDev": statistics.stdev(values) if len(values) > 1 else None}


def paired_summary(values):
    result = describe(values)
    # Five predeclared matched blocks: a descriptive Student-t interval (df=4).
    # It cannot establish transfer to another machine or the user's workspace.
    if len(values) == 5:
        half_width = 2.776445105 * statistics.stdev(values) / math.sqrt(5)
        result["descriptive95PercentTInterval"] = [result["mean"] - half_width, result["mean"] + half_width]
    result["blockValues"] = values
    return result


def diagnostics(path):
    phase = "before_probe"
    counts = defaultdict(Counter)
    urls = set()
    failures = []
    for line in path.read_text().splitlines():
        if line.startswith("XML_STUDY_PHASE "):
            phase = json.loads(line.split(" ", 1)[1])["phase"]
        elif line.startswith("XML_STUDY_HANDLER\t"):
            counts[phase]["handlerAbbreviated" if line.split("\t")[1] == "true" else "handlerFull"] += 1
        elif line.startswith("XML_STUDY_SCHEMA\t"):
            _, abbreviated, loaded, elapsed, url = line.split("\t", 4)
            counts[phase]["schemaAbbreviated" if abbreviated == "true" else "schemaFull"] += 1
            counts[phase]["schemaSucceeded" if loaded == "true" else "schemaFailed"] += 1
            urls.add(url)
            if loaded != "true":
                failures.append({"url": url, "abbreviated": abbreviated, "phase": phase})
    return {"phaseCounts": dict(counts), "uniqueSchemaUrls": len(urls), "failedLoads": failures,
            "timingExcluded": True, "note": "Parse counters and FD snapshots are diagnostic-only; no timing comparison uses this JVM"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads((args.experiment / "run-results.json").read_text())
    measured = [row for row in rows if row["measured"]]
    if any(row["status"] != "ok" for row in measured):
        raise SystemExit("Primary failures are present; investigate and report them, do not filter them out")
    if any(row.get("eclipseErrorEntries") != 0 for row in measured):
        raise SystemExit("Every primary run needs an explicit clean Eclipse error-log gate")
    cells = defaultdict(list)
    blocks = defaultdict(dict)
    for row in measured:
        cells[row["variant"]].append(row)
        key = (row["handler"], row["whitespace"])
        if key in blocks[row["block"]]:
            raise SystemExit("Duplicate cell in a randomized block")
        blocks[row["block"]][key] = row
    if len(cells) != 4 or not blocks or any(set(block) != {(0, 0), (1, 0), (0, 1), (1, 1)} for block in blocks.values()):
        raise SystemExit("The matrix is incomplete")
    metrics = {
        "workbenchReadyMs": lambda row: row["readyMs"],
        "applicationRunningMs": lambda row: row["applicationRunningMs"],
        "schemaBuildMs": lambda row: row["buildNs"] / 1_000_000,
        "settledMsIncludingQuietWindow": lambda row: row["settledMs"],
    }
    cpu_valid = all(row.get("cpuValid", False) for row in measured)
    if cpu_valid:
        metrics.update(readyProcessCpuMs=lambda row: row["readyCpuNs"] / 1_000_000,
                       buildProcessCpuMs=lambda row: row["buildCpuNs"] / 1_000_000)
    summary = {}
    contrasts = {}
    for metric, value in metrics.items():
        summary[metric] = {cell: describe([value(row) for row in values]) for cell, values in sorted(cells.items())}
        effects = defaultdict(list)
        for _, block in sorted(blocks.items()):
            a, h, w, hw = (value(block[key]) for key in [(0, 0), (1, 0), (0, 1), (1, 1)])
            effects["handlerOnlySavingsMs"].append(a - h)
            effects["formattingOnlySavingsMs"].append(a - w)
            effects["combinedSavingsMs"].append(a - hw)
            effects["extraCombinedSavingsBeyondSumMs"].append(h + w - hw - a)
            effects["handlerAverageSavingsMs"].append((a + w - h - hw) / 2)
            effects["formattingAverageSavingsMs"].append((a + h - w - hw) / 2)
        contrasts[metric] = {name: paired_summary(values) for name, values in effects.items()}
    report = {
        "method": "Randomized matched blocks of fresh JVMs, restoring each cell's prepared workspace/configuration at the same path",
        "timingScope": "JVM uptime to visible responsive workbench, then separate explicit full SchemaBuilder; not native launcher or cold OS cache",
        "blocks": len(blocks), "primaryRuns": len(measured), "cpuValidInEveryPrimaryRun": cpu_valid,
        "schemaFilesPerRun": sorted(set(row["schemaFiles"] for row in measured)),
        "markerOutcomes": sorted(set((row["markers"]["errors"], row["markers"]["warnings"], row["markers"]["information"]) for row in measured)),
        "summary": summary, "pairedContrasts": contrasts,
        "signConvention": "Positive contrast means time saved; interaction is combined savings minus sum of individual savings",
        "uncertainty": "Intervals describe five block differences under the usual Student-t assumptions; this is an exploratory reference-environment study, not a universal speed guarantee",
        "diagnostics": diagnostics(args.experiment / "runs/diagnostic-H0W0D1.log"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"blocks": len(blocks), "runs": len(measured), "schemaFiles": report["schemaFilesPerRun"],
                      "ready": summary["workbenchReadyMs"], "build": summary["schemaBuildMs"],
                      "diagnostics": report["diagnostics"]}, indent=2))


if __name__ == "__main__":
    main()
