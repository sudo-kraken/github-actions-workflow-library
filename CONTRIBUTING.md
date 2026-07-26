# Contributing

Changes should keep each file under `workflow-templates/` independent and ready
to copy into `.github/workflows/`.

Before opening a pull request:

```bash
make check
```

When changing a workflow:

- keep top-level token permissions empty;
- grant permissions per job;
- add a timeout to every job;
- pin external actions to full commit SHAs;
- set `persist-credentials: false` on checkout steps;
- keep repository-specific assumptions in clearly marked configuration blocks;
- update the README when a file is added, removed or renamed.

Avoid making one template depend on another. Users should be able to copy any
file independently.
