# Streaming compute acceptance — 2026-11-28

Shared Runtime module 12 follows the existing pure-computation selection. iPad
and Apple/Linux AArch64 interpreters can use it; Mac HVF/Linux KVM computation
thunks retain their existing disabled default. No product UI was changed.

The current native providers remain zlib 1.4, xz 5.8.4 and Zstd 1.6.0. Older
source headers are layout references, not linked implementations. Native contexts
and allocator state live in stable UnsafeCell allocations. Guest opaque bytes
are never installed into native C objects. Full state/output matching, callback
event tracking and output preflight retain original guest continuation on a miss.
See `runtime/docs/architecture/native-compute.md` for the protocol and limits.

## Performance

Same executable/data, one CPU, off/pure alternating over three samples on an
Apple M6 / 24 GiB. Ratios use median operation times. These are host interpreter
measurements, **not physical-iPad or apt/code-server measurements**.

| Library | One-shot compression, 64 KiB | Streaming compression, 4 MiB | Streaming decompression, 4 MiB |
|---|---:|---:|---:|
| zlib | 129× | 45.9× | 12.3× |
| xz | 79× | 3.9× | 8.1× |
| Zstd | 30× | 1.9× | 1.0× |

The one-shot probe also measured SHA256 ~59× and AES-128-CBC ~113×. Whole-probe
wall time, including import/startup/data preparation/verification, improved about
1.9× for the small one-shot probe and 3.5× for the streaming probe. Compression
levels: zlib 6, xz 3 and Zstd's default 3 (API level 0). Streaming input is 16 KiB
for compression, output scratch 64 KiB, compressed decoder input 64 KiB.

A 16 KiB Zstd decompression probe regressed without an eligibility gate. Such
fragments now retire the optional cache and run original code. The final 64 KiB
case is approximately neutral; no Zstd stream-decoding speedup is claimed here.
Large encoder states may also decline the cache budget. This changes neither
guest input limits nor guest allocation errors. Custom allocators retain original
initialization and callbacks. Debian zlib 1.3.1 streaming inflate and xz 5.8.1
streaming encoding retain original execution because private/dead fields differ.

## Validation

- Apple `trames-accel`: 39 unit tests; Clippy with warnings denied.
- Linux AArch64: the same 39 unit tests and shared session compilation.
- Alpine 3.22 and Debian 13 original libraries: interpreter off/pure at 1/2/4 CPUs,
  including fork during each encoder, parent/child continuation, original control
  calls, resets/dictionaries and custom zlib allocator callback accounting.
- Registered Debian Zstd trace callbacks returning zero still execute; both Zstd
  shortcuts remain original. No native Zstd steps occur in that case.
- Raw deflate and gzip roundtrips, including one-byte output fragments across the
  gzip header. The header and pending state report guest Linux OS=3 on Apple hosts.
- Numeric layout regeneration and xz copied-option-field static assertions passed.
- Source-checked iOS Rust archive and signed Release build 1.5.4 (50).

`compute-streaming-20261128.json` contains raw samples and per-kind dispatch counts.
A positive native-step count is required for supported paths; original-only
compatibility paths are asserted separately. Unchanged Vulkan/storage/graphics
acceptance is reused from the preceding validated batch.

Reproduce with `tests/performance/compute-libraries.py` and
`tests/integration/compute-streams.py`. Build the C fixtures in
`runtime/tests/fixtures/` against the exact original libraries listed in
`runtime/crates/trames-accel/src/compute-catalog.tsv`. Streaming acceptance uses
`-DFORK_TEST -DCONTROL_TEST -DINPUT_CHUNK=65536`; throughput uses
`-DN=4194304 -DINPUT_CHUNK=65536`. Trace acceptance additionally exports the test
callbacks with `-DTRACE_TEST -rdynamic`. Keep the named original libraries and
loader beside each fixture; the runners require fresh private stores.

Runtime pin: `e188a11a0925e1e8503943be7f4cfe2990b07cee`. The latest main interpreter/JIT ancestry was fast-forwarded without rewriting published commits; the iPad dependency boundary remains interpreter-only. Final probes were repeated on this merged implementation.

Build 50 was signature-verified and installed in place on the paired iPad. Automatic launch was refused because the device was locked; launch verification is pending an unlock.
