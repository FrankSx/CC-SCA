# Security Policy

## Scope

This project is an offensive-research toolkit. "Vulnerabilities in the
toolkit" means: memory-safety bugs in `_native.c`, parser bugs in the
polyglot/stego decoders (malformed input → crash/RCE in *our* decoder),
or unintended destructive behavior (e.g. Rowhammer module firing without
explicit flags).

Out of scope: results you produce by running the attacks, and the attacks
themselves (they are the point).

## Reporting

Open a private GitHub security advisory, or email the maintainer listed
in pyproject.toml. Include:

- module and version (`sca-arsenal info` output)
- reproducer input/script
- observed vs expected behavior

## Safe harbor

Good-faith research against your own clones/lab machines will never result
in legal action from the maintainer. Report what you find.
