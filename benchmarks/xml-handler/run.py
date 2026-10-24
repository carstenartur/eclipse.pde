#!/usr/bin/env python3
"""Reproduce the XML handler comparison; requires Python 3 and JDK 25."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

args = argparse.ArgumentParser(description=__doc__)
args.add_argument('--repo', type=Path, help='PDE checkout; defaults to this benchmark branch')
args.add_argument('--cpu', type=str, help='Optional Linux taskset CPU, e.g. 2')
args.add_argument('--prepare-only', action='store_true')
options = args.parse_args()
root = Path(__file__).resolve().parent
repo = options.repo.resolve() if options.repo else root.parents[1]
target = root / 'target'
target.mkdir(exist_ok=True)
inputs = json.loads((root / 'inputs.json').read_text())
patched = repo / inputs['patched_path']
if hashlib.sha256(patched.read_bytes()).hexdigest() != inputs['patched_sha256']:
    raise SystemExit('PDE handler differs from the measured patch; check out the documented revision')
for entry in inputs['downloads']:
    destination = target / entry['path']
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw_path = destination.with_suffix(destination.suffix + '.download') if entry.get('transform') else destination
    if raw_path.exists():
        data = raw_path.read_bytes()
    else:
        with urllib.request.urlopen(entry['url'], timeout=60) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise SystemExit('Checksum mismatch: ' + entry['url'])
    raw_path.write_bytes(data)
    if entry.get('transform'):
        destination.write_text(data.decode().replace('XMLDefaultHandler', 'BaselineXMLDefaultHandler'))
jdk = Path(os.environ['JAVA_HOME']) / 'bin' if os.environ.get('JAVA_HOME') else None
java = str(jdk / 'java') if jdk else shutil.which('java')
javac = str(jdk / 'javac') if jdk else shutil.which('javac')
if not java or not javac:
    raise SystemExit('Set JAVA_HOME to JDK 25')
classes = target / 'classes'
classes.mkdir(exist_ok=True)
libs = str(target / 'lib/*')
processor = os.pathsep.join(str(target / 'lib' / f) for f in ['jmh-core-1.37.jar', 'jmh-generator-annprocess-1.37.jar'])
sources = [str(p) for p in (target / 'sources').rglob('*.java')]
sources += [str(root / 'Prepare.java'), str(root / 'HandlerComparison.java'), str(patched)]
subprocess.run([javac, '--release', '25', '-cp', libs, '-processorpath', processor,
                '-processor', 'org.openjdk.jmh.generators.BenchmarkProcessor', '-d', str(classes), *sources], check=True)
classpath = str(classes) + os.pathsep + libs
subprocess.run([java, '-cp', classpath, 'bench.Prepare', '.'], cwd=target, check=True)
for name, digest in inputs['compact_sha256'].items():
    if hashlib.sha256((target / 'corpus/compact' / name).read_bytes()).hexdigest() != digest:
        raise SystemExit('Cleanup output differs: ' + name)
print('Inputs and cleanup outputs match the recorded experiment', flush=True)
if not options.prepare_only:
    command = [java, '-cp', classpath, 'org.openjdk.jmh.Main', '^bench.HandlerComparison.compare$',
               '-rf', 'json', '-rff', str(target / 'results/jmh.json')]
    if options.cpu:
        command = ['taskset', '-c', options.cpu, *command]
    with (target / 'results/jmh.log').open('w') as log:
        subprocess.run(command, cwd=target, stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([shutil.which('python3'), str(root / 'summarize.py'), str(target / 'results/jmh.json')], check=True)
