---
kind: frontend_style
name: No Frontend Style System
category: frontend_style
scope:
    - '**'
---

This repository is a backend-only toolchain for cross-compiling and packaging Nushell plugins into GitHub release assets. It contains Python scripts for manifest validation, spec generation, and release orchestration, along with GitHub Actions workflows. There are no CSS, SCSS, Tailwind, HTML templates, or any frontend styling code present in the repository. The project has no UI layer — it operates entirely as a CLI/build pipeline.