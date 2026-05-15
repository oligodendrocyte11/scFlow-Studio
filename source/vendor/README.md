# Bundled Runtime Notice

The GitHub source copy does not duplicate the full bundled macOS runtime because it is very large. The academic trial app in `../release/` contains the bundled Python/R runtime, R packages, CellAssign runtime, and local reference cache used for peer review.

To rebuild from source, prepare the same runtime folders in the project root before running `build_macos.sh`:

- `vendor/R.framework`
- `vendor/cellassign_runtime`
- `vendor/cellassign_py`
- `vendor/cellassign_Rsrc`
- `celldex_cache`

The trial behavior is controlled by `resources/trial_config.json`. Removing that file restores the regular activation workflow.
