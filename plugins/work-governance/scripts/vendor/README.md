Vendored runtime dependencies for the installed Work Governance Plugin.

`workctl.py` prepends this directory to `sys.path` before loading the
controller. Runtime imports must resolve from here or from Python's standard
library; the controller must not install packages in a target project's
`.work-governance` directory.

Included dependency:

- `yaml/` from `pyyaml==6.0.3`

Only PyYAML's pure Python package files are bundled. Platform-specific compiled
extensions are intentionally excluded so the Plugin package is not tied to the
machine that refreshed the vendor directory. The retained dist-info files are
license/provenance metadata only; platform wheel tags are not shipped.
