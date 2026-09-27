# Contributing

Thanks for taking an interest. This is a security-research toolkit: correctness
and honesty about capabilities matter more than features.

## Ground rules

1. **Authorized research only.** Do not submit changes whose primary purpose
   is targeting third-party systems. PoCs must run in lab conditions.
2. **Calibrated, not hardcoded.** Any timing threshold must come from a
   calibration routine, never a magic number copied from one host.
3. **Honest null results.** If a module can't demonstrate its effect in a
   given environment (e.g. KSM disabled, DDR5+TRR vs Rowhammer), it must say
   so in its output and docs — see `docs/BRINGUP_RESULTS.md` for the standard.
4. **Degrade gracefully.** Every attack module must detect missing native
   support / permissions / hardware and fail with an explanation, never a
   traceback dump (unless `--verbose`).

## Dev setup

```bash
pip install -e .[dev]
python -m unittest discover tests
sca-arsenal info
```

## Adding an attack module

- Implement in `sca_arsenal/<name>.py` with a docstring citing the paper
  (author/year) and stating prerequisites.
- Add a CLI subcommand in `cli.py` and an example in `examples/`.
- Add unit tests for anything testable without the hardware effect
  (codecs, framing, geometry, calibration math).
- Add a row to `docs/ATTACKS.md` and, if you ran it for real,
  `docs/BRINGUP_RESULTS.md`.

## Reporting vulnerabilities IN this toolkit

See SECURITY.md.
