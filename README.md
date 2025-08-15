# sora_imagegen_tool

A modern Python project scaffolded with a uv-based template.

## 🚀 Quickstart

1.  **Install Dev Dependencies**:
    ```bash
    uv add --dev black ruff mypy pytest pytest-cov hatch colorama pre-commit
    ```
2.  **Run Quality Checks**:
    ```bash
    make check            # preflight + tests + mypy
    # or individually: make preflight, make fmt, make lint, make test
    ```
3.  **Run the CLI**:
    ```bash
    uv run sora_imagegen_tool --name "developer"
    ```

## 🐳 Docker

-   **Build the image**: `make docker-build`
-   **Run the container**: `make docker-run`
-   **Run the full stack**: `make compose-up`
