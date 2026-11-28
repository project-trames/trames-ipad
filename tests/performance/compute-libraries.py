#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare the same guest codec probe with NativeCall disabled and enabled.

Compile runtime/tests/fixtures/native-compute-bench.c with the original
AArch64 libraries. --libraries contains original-lib*.so* and the musl loader.
This measures this host's interpreter, not physical iPad or application time.
"""
import argparse
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--runner', type=Path, required=True)
p.add_argument('--libraries', type=Path, required=True)
p.add_argument('--probe', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--samples', type=int, default=3)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
rows = []
for sample in range(a.samples):
    for mode in (('off', 'pure') if sample % 2 == 0 else ('pure', 'off')):
        store = a.output / f'store-{sample}-{mode}'
        if store.exists():
            raise SystemExit(f'Refusing to replace existing store: {store}')
        command = [str(a.runner.resolve()), '--storage', str(store.resolve()),
                   '--exec-file', '/lib/ld-musl-aarch64.so.1=' + str((a.libraries / 'ld-musl-aarch64.so.1').resolve()),
                   '--cpus', '1', '--accelerator', mode, '--metrics',
                   '--max-instructions', '10000000000',
                   '--exec-file', '/tmp/probe=' + str(a.probe.resolve())]
        for name in ('libz.so.1', 'liblzma.so.5', 'libzstd.so.1', 'libcrypto.so.3'):
            command += ['--file', '/usr/lib/' + name + '=' + str((a.libraries / ('original-' + name)).resolve())]
        start = time.monotonic()
        result = subprocess.run([*command, '--guest', '/tmp/probe'], capture_output=True, timeout=240)
        elapsed = time.monotonic() - start
        for suffix, content in [('stdout', result.stdout), ('stderr', result.stderr)]:
            (a.output / f'{sample}-{mode}.{suffix}').write_bytes(content)
        if result.returncode:
            raise SystemExit(f'{mode}: exit {result.returncode}; see saved logs')
        metrics = json.loads(next(line.removeprefix('trames native metrics: ')
                                 for line in result.stderr.decode().splitlines()
                                 if line.startswith('trames native metrics: ')))
        rows.append({'sample': sample, 'mode': mode, 'wall_seconds': elapsed,
                     'operations': [json.loads(line) for line in result.stdout.decode().splitlines() if line.startswith('{')],
                     'compute_calls': metrics['compute_calls'], 'worker_calls': metrics['worker_calls'],
                     'compute_fallbacks': metrics['compute_fallbacks'],
                     'stream_native_steps': metrics.get('stream_native_steps', 0)})
        (a.output / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        shutil.rmtree(store)
for operation in rows[0]['operations']:
    name = operation['operation']
    medians = {mode: statistics.median(op['nanoseconds'] for row in rows if row['mode'] == mode
                                      for op in row['operations'] if op['operation'] == name)
               for mode in ('off', 'pure')}
    print(name, json.dumps(medians), f"{medians['off'] / medians['pure']:.1f}x")
