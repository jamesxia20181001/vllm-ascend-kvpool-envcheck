# Repository Guidelines

This repository hosts `kvpool_envcheck.py`, an offline pre-deployment environment checker for vLLM-Ascend KV Cache Pool. It runs inside the vLLM-Ascend Docker container, does not access the network, and is read-only unless `--fix` is explicitly passed. Rules and supported scope live in `rules.json`; design rationale lives in `DESIGN.md`.

## Project Structure & Module Organization

- `kvpool_envcheck.py` — single-file checker implementation; the full CLI entrypoint and all probes/parsers.
- `rules.json` — rule catalog consumed at runtime; CLI help (`-h`) is generated from it.
- `tests/test_kvpool_envcheck.py` — `unittest` suite, loads the module dynamically via `importlib.util`.
- `artifacts/` — vendored helper scripts (`mem_scan.py`, `hccs_test_a3.py`) tracked with `artifacts/manifest.json` (sha256 verification).
- `DESIGN.md` — architecture and judgement logic.
- `README.md` — user-facing usage (Chinese).
- `stub/` — pure-Docker simulation environment (no monkeypatch) that lets the checker run on plain x86_64/aarch64 hosts without real Ascend hardware. `stub/gen_profiles.py` generates A2/A3 profile data (sysfs NUMA topology, page-size independent); `stub/gen_kpageflags.py` generates the fake `/proc/kpageflags` at container startup using the runtime page size (fixes aarch64 64K-page alignment); `stub/Dockerfile` + `stub/entrypoint.sh` assemble the simulated `/proc`, sysfs, `npu-smi`, `hccn_tool`, and fake `torch`/`torch_npu` modules. Profile data (`stub/profiles/`) is build-generated and git-ignored. See `stub/README.md` (Chinese) for the full mechanism.

## Build, Test, and Development Commands

No build step. Python 3.12+ only (uses `from __future__ import annotations`, dataclasses, `importlib.metadata`).

```bash
# Run the checker (dry run, report to stdout)
python3 kvpool_envcheck.py --hardware A3 --backend memcache \
  --managed-memory-mb 32768 --deployment-mode single-node --link-type hccs

# Save results to ./results (writes one .result.json + one .report.txt pair)
python3 kvpool_envcheck.py ... --output-dir ./results

# Full CLI help is generated from rules.json
python3 kvpool_envcheck.py -h

# Run the test suite
python3 -m unittest tests.test_kvpool_envcheck
```

## Coding Style & Naming Conventions

- Python 3.12, 4-space indentation, LF line endings, ASCII where possible (progress strings may contain Chinese).
- Module-level constants `UPPER_SNAKE`; functions and dataclasses `snake_case`; classes `PascalCase`.
- Type hints required on public surfaces; prefer `from typing import ...` imports grouped as in the existing header.
- No external runtime dependencies — stdlib only. Do not add third-party imports.
- No formatter configured; match the surrounding style manually.

## Testing Guidelines

- Framework: stdlib `unittest`. Tests live in `tests/test_kvpool_envcheck.py`.
- Naming: `test_<topic>_<expected_behaviour>` (e.g. `test_hccs_busy_skip_remains_blocking`).
- The suite loads `kvpool_envcheck.py` by file path, so no package install is needed. Run the whole suite before pushing:
  ```bash
  python3 -m unittest tests.test_kvpool_envcheck -v
  ```
- When adding a probe or parser, add a focused unit test covering both pass and blocking cases. Keep tests hermetic: mock `subprocess` / filesystem via `unittest.mock`, do not touch real NPU/`/proc` paths.

### Docker stub (end-to-end simulation)

The `stub/` image runs the unmodified checker against a simulated A2/A3 environment on any host. It needs `--cap-add SYS_ADMIN` for bind-mounts over `/proc` and sysfs.

```bash
# Build (x86_64 or aarch64)
docker build -t kvpool-envcheck-stub -f stub/Dockerfile .

# A2 default (single-node RoCE) — 8 rules PASS
docker run --rm --cap-add SYS_ADMIN --security-opt apparmor=unconfined kvpool-envcheck-stub

# A3 single-node HCCS — 8 PASS
docker run --rm --cap-add SYS_ADMIN --security-opt apparmor=unconfined -e STUB_PROFILE=a3 \
  kvpool-envcheck-stub \
  python3 kvpool_envcheck.py --hardware A3 --backend memcache \
    --managed-memory-mb 32768 --deployment-mode single-node --link-type hccs
```

A3 dynamic rules (HCCS-002, ROCE-002) exercise the original `artifacts/` scripts against faked dependencies, so they PASS in the stub; this validates the checker's plumbing, not real data-path correctness. Real hardware still requires `torch_npu`/HCCL and Ascend devices.

`stub/smoke_test.sh` machine-checks the README's PASS-count claims (A2 8 PASS, A3 single-node 8 PASS, A3 multi-node 9 PASS + 1 MANUAL_REQUIRED) by building the image, running each scenario, and asserting counts via `stub/assert_result.py`. Run it before pushing stub changes.

## Commit & Pull Request Guidelines

History uses short imperative subjects with a body and a `Signed-off-by` trailer (DCO). Examples from `git log`:

```
Relax A3 HDK minimum to 25.5

Signed-off-by: doubin <doubin@huawei.com>
```

- Subject line: imperative mood, ≤ ~60 chars, no `feat:`/`fix:` prefixes.
- Body: explain why, reference rule IDs (`MEM-001`, `HDK-001`, ...) when changing behaviour.
- Include `Signed-off-by: Your Name <email>` (DCO) on every commit.
- PRs must update `rules.json` when changing thresholds or supported combinations, keep `artifacts/manifest.json` sha256 in sync if a vendored script changes, and add/adjust tests. Self-review against `DESIGN.md` before requesting review.
