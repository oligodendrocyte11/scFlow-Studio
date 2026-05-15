"""
Merge and clustering: combine samples, normalize data, select HVGs, run PCA/UMAP/t-SNE, and cluster cells.
"""
import json
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox,
    QLineEdit, QMessageBox, QListWidget, QAbstractItemView,
    QLabel, QPushButton, QToolButton,
)
from PySide6.QtCore import Qt
from ui.pages.base_page import BasePage
from ui.help_content import build_step_help


class MergeClusterPage(BasePage):
    STEP_ID = "merge_cluster"
    STEP_NAME = "⑤ Merge and Clustering"

    def setup_params_ui(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        grp_merge = QGroupBox("Merge Parameters")
        form_m = QFormLayout(grp_merge)

        self.cmb_merge_mode = QComboBox()
        self.cmb_merge_mode.addItems(["Direct merge", "Batch integration (RPCA/Harmony/CCA)"])

        self.list_samples = QListWidget()
        self.list_samples.setSelectionMode(QAbstractItemView.MultiSelection)
        self.list_samples.setMaximumHeight(120)

        self.chk_add_prefix = QCheckBox("Add sample prefix")
        self.chk_add_prefix.setChecked(True)

        self.cmb_norm = QComboBox()
        self.cmb_norm.addItems(["LogNormalize", "SCT (reserved)"])

        self.spn_scale_factor = QSpinBox()
        self.spn_scale_factor.setRange(1000, 100000)
        self.spn_scale_factor.setValue(10000)

        form_m.addRow("Integration mode:", self.cmb_merge_mode)
        form_m.addRow("Samples to merge:", self.list_samples)
        form_m.addRow("", self.chk_add_prefix)
        form_m.addRow("Normalization:", self.cmb_norm)
        form_m.addRow("Scale factor:", self.spn_scale_factor)
        layout.addWidget(grp_merge)

        grp_cluster = QGroupBox("Clustering and Reduction Parameters")
        form_c = QFormLayout(grp_cluster)

        self.cmb_hvg_method = QComboBox()
        self.cmb_hvg_method.addItems(["vst", "dispersion", "mean.var.plot"])

        self.txt_regress = QLineEdit("percent.mt")

        self.spn_resolution = QDoubleSpinBox()
        self.spn_resolution.setRange(0.05, 5.0)
        self.spn_resolution.setDecimals(2)
        self.spn_resolution.setSingleStep(0.1)
        self.spn_resolution.setValue(self.app_config.cluster_resolution)

        self.chk_umap = QCheckBox("Run UMAP")
        self.chk_umap.setChecked(True)
        self.chk_tsne = QCheckBox("Run tSNE")
        self.chk_tsne.setChecked(False)
        self.chk_umap.toggled.connect(self._sync_reduction_choice)
        self.chk_tsne.toggled.connect(self._sync_reduction_choice)

        self.cmb_primary_reduction = QComboBox()
        self.cmb_primary_reduction.addItems(["umap", "tsne"])
        self.cmb_primary_reduction.currentTextChanged.connect(self._sync_primary_reduction)

        form_c.addRow("HVG method:", self.cmb_hvg_method)
        form_c.addRow("Scale regression variables:", self.txt_regress)
        form_c.addRow("Clustering resolution:", self.spn_resolution)
        form_c.addRow("", self.chk_umap)
        form_c.addRow("", self.chk_tsne)
        form_c.addRow("Primary reduction:", self.cmb_primary_reduction)

        self.lbl_recommendation = QLabel(
            "Recommended defaults: use HVG 3000, PCA 50, and dims 1:30. "
            "Open Advanced Parameters if you need to adjust these settings after checking the elbow plot."
        )
        self.lbl_recommendation.setWordWrap(True)
        self.lbl_recommendation.setStyleSheet("color:#5F6B7A; font-size:11px;")
        form_c.addRow("", self.lbl_recommendation)

        layout.addWidget(grp_cluster)

        self.btn_toggle_advanced = QToolButton()
        self.btn_toggle_advanced.setText("Show Advanced Parameters")
        self.btn_toggle_advanced.setCheckable(True)
        self.btn_toggle_advanced.setChecked(False)
        self.btn_toggle_advanced.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_toggle_advanced.setArrowType(Qt.RightArrow)
        self.btn_toggle_advanced.toggled.connect(self._toggle_advanced_params)
        layout.addWidget(self.btn_toggle_advanced)

        self.advanced_box = QGroupBox("Advanced Parameters")
        self.advanced_box.setVisible(False)
        form_adv = QFormLayout(self.advanced_box)

        self.spn_hvg = QSpinBox()
        self.spn_hvg.setRange(500, 10000)
        self.spn_hvg.setValue(self.app_config.cluster_hvg_number)

        self.spn_npcs = QSpinBox()
        self.spn_npcs.setRange(5, 100)
        self.spn_npcs.setValue(self.app_config.cluster_npcs)

        self.txt_dims = QLineEdit(self.app_config.cluster_dims)
        self.txt_dims.editingFinished.connect(self._sync_npcs_with_dims)

        self.lbl_advanced_hint = QLabel(
            "Too few HVGs may compress biological heterogeneity; too many may amplify noise. "
            "Too few PCs may merge related populations, while too many PCs may add noise to the neighbor graph."
        )
        self.lbl_advanced_hint.setWordWrap(True)
        self.lbl_advanced_hint.setStyleSheet("color:#5F6B7A; font-size:11px;")

        self.btn_restore_advanced = QPushButton("Restore Recommended Defaults")
        self.btn_restore_advanced.clicked.connect(self._restore_advanced_defaults)

        form_adv.addRow("HVG count (nfeatures):", self.spn_hvg)
        form_adv.addRow("PCA upper limit (npcs):", self.spn_npcs)
        form_adv.addRow("PCs used for neighbors / clustering / reduction (dims):", self.txt_dims)
        form_adv.addRow("", self.lbl_advanced_hint)
        form_adv.addRow("", self.btn_restore_advanced)
        layout.addWidget(self.advanced_box)

        self.bind_help_refresh(
            self.cmb_merge_mode,
            self.list_samples,
            self.chk_add_prefix,
            self.cmb_norm,
            self.spn_scale_factor,
            self.cmb_hvg_method,
            self.txt_regress,
            self.spn_resolution,
            self.chk_umap,
            self.chk_tsne,
            self.cmb_primary_reduction,
            self.btn_toggle_advanced,
            self.spn_hvg,
            self.spn_npcs,
            self.txt_dims,
        )
        return container

    def _toggle_advanced_params(self, checked: bool):
        self.advanced_box.setVisible(checked)
        self.btn_toggle_advanced.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.btn_toggle_advanced.setText(
            "Hide Advanced Parameters" if checked else "Show Advanced Parameters"
        )
        self.refresh_help()

    def _restore_advanced_defaults(self):
        cfg = self.app_config
        self.spn_hvg.setValue(cfg.cluster_hvg_number)
        self.spn_npcs.setValue(cfg.cluster_npcs)
        self.txt_dims.setText(cfg.cluster_dims)
        self.refresh_help()

    def _parse_dims_upper(self, dims_text: str) -> int:
        text = (dims_text or "").strip()
        if not text:
            raise ValueError("dims cannot be empty")
        if ":" in text:
            start_text, end_text = text.split(":", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if start <= 0 or end < start:
                raise ValueError("dims range is invalid")
            return end
        values = [int(token.strip()) for token in text.replace(";", ",").split(",") if token.strip()]
        if not values:
            raise ValueError("dims cannot be empty")
        if min(values) <= 0:
            raise ValueError("dims must contain positive integers")
        return max(values)

    def _sync_npcs_with_dims(self):
        try:
            dims_upper = self._parse_dims_upper(self.txt_dims.text())
        except ValueError:
            return
        if self.spn_npcs.value() < dims_upper:
            self.spn_npcs.setValue(dims_upper)

    def _collect_selected_samples(self) -> list[str]:
        selected = []
        for i in range(self.list_samples.count()):
            item = self.list_samples.item(i)
            if item.isSelected():
                selected.append(item.text())
        return selected

    def get_params(self) -> dict:
        try:
            dims_upper = self._parse_dims_upper(self.txt_dims.text())
        except ValueError:
            dims_upper = self.spn_npcs.value()
        safe_npcs = max(self.spn_npcs.value(), dims_upper)
        return {
            "merge_mode": self.cmb_merge_mode.currentText(),
            "selected_samples": self._collect_selected_samples(),
            "add_prefix": self.chk_add_prefix.isChecked(),
            "norm_method": self.cmb_norm.currentText(),
            "scale_factor": self.spn_scale_factor.value(),
            "hvg_method": self.cmb_hvg_method.currentText(),
            "hvg_number": self.spn_hvg.value(),
            "regress_vars": self.txt_regress.text(),
            "npcs": safe_npcs,
            "dims": self.txt_dims.text().strip(),
            "resolution": self.spn_resolution.value(),
            "run_umap": self.chk_umap.isChecked(),
            "run_tsne": self.chk_tsne.isChecked(),
            "primary_reduction": self.cmb_primary_reduction.currentText(),
            "seed": self.app_config.default_seed,
        }

    def _load_batch_config(self) -> dict:
        if not self.project:
            return {
                "batch_enabled": False,
                "batch_key": "sample",
                "batch_method": "RPCA (Recommended)",
                "batch_status": "skipped",
            }
        config_path = os.path.join(self.project.cache_subdir("batch"), "batch_config.json")
        if not os.path.exists(config_path):
            return {
                "batch_enabled": False,
                "batch_key": "sample",
                "batch_method": "RPCA (Recommended)",
                "batch_status": "skipped",
            }
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return {
                "batch_enabled": False,
                "batch_key": "sample",
                "batch_method": "RPCA (Recommended)",
                "batch_status": "skipped",
            }
        return {
            "batch_enabled": bool(data.get("batch_enabled", False)),
            "batch_key": str(data.get("batch_key", "sample")),
            "batch_method": str(data.get("batch_method", "RPCA (Recommended)")),
            "batch_status": str(data.get("batch_status", "enabled" if data.get("batch_enabled", False) else "skipped")),
        }

    def reset_params(self):
        cfg = self.app_config
        self.cmb_merge_mode.setCurrentIndex(0)
        self.chk_add_prefix.setChecked(True)
        self.cmb_norm.setCurrentIndex(0)
        self.spn_scale_factor.setValue(10000)
        self.cmb_hvg_method.setCurrentText("vst")
        self.txt_regress.setText("percent.mt")
        self.spn_resolution.setValue(cfg.cluster_resolution)
        self.chk_umap.setChecked(True)
        self.chk_tsne.setChecked(False)
        self.cmb_primary_reduction.setCurrentText("umap")
        self._restore_advanced_defaults()
        if self.list_samples.count():
            self.list_samples.selectAll()

    def _sync_reduction_choice(self):
        sender = self.sender()
        if sender == self.chk_umap and self.chk_umap.isChecked():
            self.chk_tsne.blockSignals(True)
            self.chk_tsne.setChecked(False)
            self.chk_tsne.blockSignals(False)
            self.cmb_primary_reduction.setCurrentText("umap")
        elif sender == self.chk_tsne and self.chk_tsne.isChecked():
            self.chk_umap.blockSignals(True)
            self.chk_umap.setChecked(False)
            self.chk_umap.blockSignals(False)
            self.cmb_primary_reduction.setCurrentText("tsne")

        if not self.chk_umap.isChecked() and not self.chk_tsne.isChecked():
            preferred = self.cmb_primary_reduction.currentText() or "umap"
            if preferred == "tsne":
                self.chk_tsne.blockSignals(True)
                self.chk_tsne.setChecked(True)
                self.chk_tsne.blockSignals(False)
            else:
                self.chk_umap.blockSignals(True)
                self.chk_umap.setChecked(True)
                self.chk_umap.blockSignals(False)
        self.refresh_help()

    def _sync_primary_reduction(self, reduction: str):
        use_umap = reduction != "tsne"
        self.chk_umap.blockSignals(True)
        self.chk_tsne.blockSignals(True)
        self.chk_umap.setChecked(use_umap)
        self.chk_tsne.setChecked(not use_umap)
        self.chk_umap.blockSignals(False)
        self.chk_tsne.blockSignals(False)
        self.refresh_help()

    def get_help_html(self) -> str:
        return build_step_help("merge_cluster", {
            "norm_method": self.cmb_norm.currentText(),
            "hvg_method": self.cmb_hvg_method.currentText(),
            "hvg_number": self.spn_hvg.value(),
            "npcs": self.spn_npcs.value(),
            "dims": self.txt_dims.text().strip() or self.app_config.cluster_dims,
            "regress_vars": self.txt_regress.text().strip() or "percent.mt",
            "resolution": self.spn_resolution.value(),
            "primary_reduction": self.cmb_primary_reduction.currentText(),
            "run_umap": self.chk_umap.isChecked(),
            "run_tsne": self.chk_tsne.isChecked(),
        })

    def on_project_loaded(self, project):
        super().on_project_loaded(project)
        self._refresh_samples()
        self.refresh_help()

    def on_page_entered(self):
        self._refresh_samples()
        self.refresh_help()

    def _refresh_samples(self):
        self.list_samples.clear()
        if self.project and self.project.samples:
            for sample in self.project.samples:
                self.list_samples.addItem(sample.name)
            self.list_samples.selectAll()
        self.refresh_help()

    def run_step(self):
        if not self.require_project():
            return

        adjust_msg = ""
        if not self._collect_selected_samples():
            QMessageBox.warning(self, "Notice", "Please select at least one sample for merging.")
            return

        try:
            dims_upper = self._parse_dims_upper(self.txt_dims.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Notice", f"Invalid clustering PCs (dims) format: {exc}\nUse a format such as 1:30 or 1,2,3.")
            return

        if self.spn_npcs.value() < dims_upper:
            self.spn_npcs.setValue(dims_upper)
            adjust_msg = f"PCA components were increased to {dims_upper} to match dims={self.txt_dims.text().strip()}。"

        self.clear_log()
        self.append_log("=== Merge and Clustering ===")
        if adjust_msg:
            self.append_log(adjust_msg)

        params = self.get_params()
        batch_config = self._load_batch_config()
        if self.cmb_merge_mode.currentIndex() == 0:
            # Direct merge mode does not rerun batch correction; choose batch integration on this page if needed.
            batch_config = {
                "batch_enabled": False,
                "batch_key": batch_config.get("batch_key", "sample"),
                "batch_method": batch_config.get("batch_method", "RPCA (Recommended)"),
                "batch_status": "skipped",
            }
        params.update(batch_config)
        self.append_log(
            "Batch correction config: "
            f"enabled={params['batch_enabled']}, status={params['batch_status']}, batch column={params['batch_key']}, method={params['batch_method']}"
        )

        samples_rds = []
        selected_names = set(params["selected_samples"])
        for sample in self.project.samples:
            if selected_names and sample.name not in selected_names:
                continue
            rds_path = os.path.join(
                self.project.cache_subdir("doublet"),
                f"{sample.name}_singlet.rds"
            ).replace("\\", "/")
            samples_rds.append({
                "name": sample.name,
                "group": sample.group,
                "rds_path": rds_path,
            })
        params["samples"] = samples_rds
        params["merge_cache_dir"] = self.project.cache_subdir("merged").replace("\\", "/")
        params["cluster_cache_dir"] = self.project.cache_subdir("clustering").replace("\\", "/")

        output_dir = self.project.cache_subdir("clustering")

        self.task_runner.run_r_script(
            script_name="05_cluster.R",
            params=params,
            output_dir=output_dir,
            step_name="Merge and Clustering",
        )
        self.project.step_status["merge_cluster"] = "running"
        idx = self.main_window.get_step_index("merge_cluster")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "running")

    def on_step_finished(self, result):
        self.append_log("=== Merge and Clustering Finished ===")
        self.project.step_status["merge_cluster"] = "done"
        idx = self.main_window.get_step_index("merge_cluster")
        if idx >= 0:
            self.main_window.sidebar.set_step_status(idx, "done")

        summary = result.summary if hasattr(result, "summary") else (
            result if isinstance(result, dict) else {}
        )

        if "cluster_stats" in summary:
            stats = summary["cluster_stats"]
            headers = ["Cluster", "Cells", "Percent"]
            data = [
                [str(item.get("cluster", "")), str(item.get("count", "")), item.get("percent", "")]
                for item in stats
            ]
            self.set_result_table(data, headers)

        figures = getattr(result, "figures", summary.get("figures", []))
        cache_dir = self.project.cache_subdir("clustering")
        preferred_preview = ""
        preview_names = {
            "clustering_global": "Clustering Global",
            "clustering_split_by_group": "Clustering Split by Group",
            "umap_groups": "UMAP by Group",
            "variable_features": "Variable Features",
            "elbow_plot": "Elbow Plot",
            "tsne_clusters": "tSNE Clusters",
        }
        for fig in figures:
            fig_path = fig if os.path.isabs(fig) else os.path.join(cache_dir, fig)
            if os.path.isfile(fig_path):
                name = os.path.splitext(os.path.basename(fig_path))[0]
                self.main_window.add_preview_item(
                    name=preview_names.get(name, name),
                    path=fig_path,
                    item_type="figure",
                    step="Cluster",
                )
                if name == "clustering_global":
                    preferred_preview = fig_path
                elif not preferred_preview and name == "clustering_split_by_group":
                    preferred_preview = fig_path
        if preferred_preview:
            self.main_window.show_preview_image(preferred_preview, "Clustering Overview")
