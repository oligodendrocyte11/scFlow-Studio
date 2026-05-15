# scFlow Studio Project Structure

- `main.py`: application entry point.
- `app/`: application configuration and main window.
- `core/`: project management, task runner, R bridge, cache handling, import logic, and runtime path resolution.
- `ui/`: toolbar, sidebar, preview panel, settings, help content, and workflow pages.
- `widgets/`: reusable image viewer and UI widgets.
- `r_scripts/`: Seurat-based backend scripts and shared R utilities.
- `resources/`: styles, static assets, license resources, templates, and bundled references.
- `vendor/`: bundled macOS runtime components used for portable execution.
- `celldex_cache/`: local celldex reference cache for offline SingleR annotation.
- `build_macos.sh`: macOS packaging entry point.
- `distribute_macos.sh`: optional signing/notarization-oriented distribution helper.
