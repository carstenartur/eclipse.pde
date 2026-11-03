#!/usr/bin/env python3
"""Fetch matching official source bundles for schemas absent from SDK binaries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def manifest(jar):
    with zipfile.ZipFile(jar) as archive:
        raw = archive.read("META-INF/MANIFEST.MF").decode("utf-8").replace("\r\n", "\n")
    return dict(line.split(": ", 1) for line in raw.replace("\n ", "").split("\n\n", 1)[0].splitlines() if ": " in line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eclipse-home", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    wanted = []
    declared = present = 0
    for jar in sorted((args.eclipse_home / "plugins").glob("*.jar")):
        with zipfile.ZipFile(jar) as archive:
            names = set(archive.namelist())
            missing = []
            for descriptor in ("plugin.xml", "fragment.xml"):
                if descriptor not in names:
                    continue
                for point in ET.fromstring(archive.read(descriptor)).findall("extension-point"):
                    path = point.get("schema")
                    if path:
                        declared += 1
                        if path in names:
                            present += 1
                        else:
                            missing.append(path)
        if missing:
            metadata = manifest(jar)
            bundle = metadata["Bundle-SymbolicName"].split(";")[0]
            version = metadata["Bundle-Version"]
            resolved = jar.resolve()
            if "/m2-integration/" in str(resolved):
                relative = str(resolved).split("/m2-integration/", 1)[1]
                url = "https://repo.maven.apache.org/maven2/" + relative[:-4] + "-sources.jar"
            else:
                match = re.search(r"-(\d+\.\d+[^/]*)\.jar$", resolved.name)
                if not match:
                    raise ValueError(f"Cannot identify Maven version of {resolved}")
                maven_version = match.group(1)
                group = "pde" if bundle.startswith("org.eclipse.pde.") else "jdt" if bundle.startswith("org.eclipse.jdt.") else "platform"
                url = f"https://repo.maven.apache.org/maven2/org/eclipse/{group}/{bundle}/{maven_version}/{bundle}-{maven_version}-sources.jar"
            wanted.append({"bundle": bundle, "version": version, "url": url, "missingBinaryPaths": missing})

    def fetch(item):
        item = dict(item)
        target = args.output_directory / (item["bundle"] + ".source_" + item["version"] + ".jar")
        if not target.exists():
            temporary = target.with_suffix(".part")
            result = subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "90",
                                     item["url"], "--output", str(temporary)], text=True, capture_output=True)
            if result.returncode:
                temporary.unlink(missing_ok=True)
                item.update(status="download_failed", error=result.stderr.strip())
                return item
            temporary.replace(target)
        metadata = manifest(target)
        source_header = metadata.get("Eclipse-SourceBundle", "")
        if source_header.split(";")[0] != item["bundle"] or metadata.get("Bundle-Version") != item["version"]:
            raise ValueError(f"Source bundle does not match binary: {target}: {source_header}")
        with zipfile.ZipFile(target) as archive:
            names = set(archive.namelist())
            found = [path for path in item["missingBinaryPaths"] if path in names]
        item.update(status="verified", file=str(target.resolve()), sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    sourcePathsFound=found, stillMissing=[path for path in item["missingBinaryPaths"] if path not in found])
        return item

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(fetch, wanted))
    report = {"declaredSchemaPaths": declared, "presentInBinary": present,
              "sourceBundlesRequested": len(wanted), "sources": results}
    output = args.output_directory / "schema-source-manifest.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"declared": declared, "binary": present, "sourceFound": sum(len(x.get("sourcePathsFound", [])) for x in results),
                      "failedDownloads": sum(x["status"] != "verified" for x in results), "report": str(output)}))
    if any(x["status"] != "verified" or x.get("stillMissing") for x in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
