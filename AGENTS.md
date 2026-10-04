# Robot Agent engineering entry

Apply the host's shared engineering entry. Resolve shared guide locations from
that host; do not copy personal paths or model/account configuration here.

- [README](README.md) is the project/preview entry. [Application contracts](docs/README.md)
  own task behavior; [Testing](docs/TESTING.md) owns verification scope and limits.
- [Contributing](CONTRIBUTING.md) covers onboarding.
- This repository owns goal, task state, budget, visual proposals and task reports.
  Robot Harness owns execution authority, native resources and Core settlement.
  Depend on Harness in one direction; do not import private Host/Core internals.
- Model input is task context and the measurements declared by each application:
  ALOHA camera/joints or navigation public map pose/time/sensor health. Simulator
  ground-truth contacts/poses and independent evaluation never drive decisions.
- Never retry an ambiguous submission, reset automatically, fabricate settlement
  or promote a visual assessment to an independently verified task verdict.
- Tests: `PYTHONPATH=src python -m unittest discover -s tests -v`.
  Real model/physics checks require the operator's explicit environment and paths;
  mocks and configured CI do not establish those results.
- [ACT / ALOHA setup](skills/aloha/README.md) owns the pinned skill environment,
  bundled candidate worker and explicit public download/offline migration path.
  Its private candidate transport requires the exact Harness dependency from
  `workspace.repos`; do not present it as a stable plugin API.
- Keep runs, checkpoints, private logs and machine configuration outside Git.
  No source snapshots, routine hashes or parallel acceptance registries.
