# Aech CLI Translator

Enterprise translation workflow that leverages the Aech runtime. The CLI wraps
three agents (translate, back-translate, audit) and exposes a single
`translate` command.

## Manifest-Based `--help`

Aech installs each capability by calling `--help` on every discovered binary.
Because the CLI renders interactive Rich output, we intercept the top-level
`--help` invocation and return a JSON manifest instead. The manifest matches the
structure the installer already understands (same schema as `manifest.json`).

Implementation details:

1. `aech_cli_translator.main` defines the manifest dictionary and helper
   functions (`_should_emit_manifest` + `_print_manifest`).
2. The new `run()` entry point checks if the provided argv is simply `--help` or
   `-h`. If so, it prints the manifest JSON and exits before Typer renders its
   UI. Otherwise it forwards control to the Typer app.
3. `pyproject.toml` now points the console script to `run` so the behavior is
   consistent whether you execute `python -m ...` or the installed binary.

### Applying This Pattern to Other CLIs

When creating additional Agent Aech CLIs, copy the following approach:

1. Define a manifest dictionary that matches the format above (name, type,
   description, command, actions array, available_in_sandbox flag). Keep it in
   your CLI module so it is always available at runtime.
2. Create a lightweight wrapper function that detects a bare `--help`/`-h` and
   prints `json.dumps(manifest, indent=2)` before exiting.
3. Expose that wrapper via `[project.scripts]` in `pyproject.toml` (or whatever
   entry-point mechanism you use) so the custom logic runs before your Typer/
   Click app.
4. If you maintain a standalone `manifest.json`, keep it in the same shape so
   consumers get identical metadata whether they read the file or call
   `--help`.

With this pattern Aech's installer receives a machine-readable manifest while
developers still have access to standard sub-command help (`translate --help`).
