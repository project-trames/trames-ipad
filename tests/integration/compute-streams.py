#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Original codec ABI, fork and continuation acceptance using the real CLI."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--runner', type=Path, required=True)
p.add_argument('--fixtures', type=Path, action='append', required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--probe', type=Path)
p.add_argument('--cpus', type=int, nargs='+', default=[1,2,4])
p.add_argument('--expect-original-zstd', action='store_true')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
rows = []
for family in a.fixtures:
    musl = (family / 'ld-musl-aarch64.so.1').exists()
    loader = 'ld-musl-aarch64.so.1' if musl else 'ld-linux-aarch64.so.1'
    for cpus in a.cpus:
        for mode in ('off', 'pure'):
            key = f'{family.name}-{cpus}-{mode}'
            store = a.output / (key + '-store')
            if store.exists():
                raise SystemExit(f'Refusing to replace existing store: {store}')
            command = [str(a.runner.resolve()), '--storage', str(store.resolve()),
                       '--exec-file', '/lib/' + loader + '=' + str((family / loader).resolve()),
                       '--cpus', str(cpus), '--accelerator', mode, '--metrics',
                       '--max-instructions', '5000000000',
                       '--exec-file', '/tmp/probe=' + str((a.probe or (family / 'compute-stream-probe')).resolve())]
            if not musl:
                command += ['--file', '/lib/aarch64-linux-gnu/libc.so.6=' + str((family / 'libc.so.6').resolve())]
            for name in ('libz.so.1', 'liblzma.so.5', 'libzstd.so.1', 'libcrypto.so.3'):
                command += ['--file', '/usr/lib/' + name + '=' + str((family / ('original-' + name)).resolve())]
            began = time.monotonic()
            result = subprocess.run([*command, '--guest', '/tmp/probe'], capture_output=True, timeout=120)
            elapsed = time.monotonic() - began
            for suffix, content in [('stdout', result.stdout), ('stderr', result.stderr)]:
                (a.output / (key + '.' + suffix)).write_bytes(content)
            assert result.returncode == 0, (key, result.returncode, result.stderr[-3000:])
            lines = result.stderr.decode().splitlines()
            metrics = json.loads(next(line.removeprefix('trames native metrics: ') for line in lines if line.startswith('trames native metrics: ')))
            native = metrics['stream_native_operations']
            if mode == 'pure':
                expected = [True, family.name != 'debian13', True, not a.expect_original_zstd, not a.expect_original_zstd]
                assert all((n > 0) == required for n, required in zip(native, expected)), (key,native)
            else:
                assert all(n == 0 for n in native), (key,native)
            assert metrics['worker_calls'] == metrics['compute_calls'] + metrics['stream_calls'], key
            row = {'case': key, 'seconds': elapsed, 'exit': result.returncode,
                   'native_steps': native, 'learns': metrics['stream_learn_operations'],
                   'cache_misses': metrics['stream_cache_misses']}
            rows.append(row)
            (a.output / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
            print(json.dumps(row), flush=True)
            shutil.rmtree(store)
