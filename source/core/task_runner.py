from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal


class _TaskWorker(QObject):
    finished = Signal(object)
    error = Signal(str, str, str)
    log_output = Signal(str)
    progress = Signal(int, str)

    def __init__(self, r_bridge, script_name: str, params: dict, output_dir: str, step_name: str):
        super().__init__()
        self.r_bridge = r_bridge
        self.script_name = script_name
        self.params = params
        self.output_dir = output_dir
        self.step_name = step_name

    def run(self):
        self.log_output.emit(f"[TaskRunner] Starting task: {self.step_name}")
        result = self.r_bridge.call_script(
            script_name=self.script_name,
            params=self.params,
            output_dir=self.output_dir,
            log_callback=self.log_output.emit,
            progress_callback=self.progress.emit,
        )

        if result.success:
            self.log_output.emit("[TaskRunner] Task completed")
            self.finished.emit(result)
            return

        summary = ""
        detail = result.error_message or ""
        if isinstance(result.summary, dict):
            summary = (
                str(result.summary.get("message", "") or "")
                or str(result.summary.get("summary", "") or "")
                or detail
            )
            detail = str(result.summary.get("detail", "") or detail)
        summary = summary or "Failed"
        self.log_output.emit(f"[TaskRunner] Task failed: {summary}")
        self.error.emit(self.step_name, summary, detail)


class TaskRunner(QObject):
    progress = Signal(int, str)
    log_output = Signal(str)
    finished = Signal(object)
    error_occurred = Signal(str, str, str)

    def __init__(self, r_bridge, parent=None):
        super().__init__(parent)
        self.r_bridge = r_bridge
        self._thread: QThread | None = None
        self._worker: _TaskWorker | None = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def run_r_script(self, script_name: str, params: dict, output_dir: str, step_name: str):
        if self._is_running:
            self.log_output.emit("[TaskRunner] A task is already running.")
            return

        self._thread = QThread(self)
        self._worker = _TaskWorker(self.r_bridge, script_name, params, output_dir, step_name)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.emit)
        self._worker.log_output.connect(self.log_output.emit)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)

        self._is_running = True
        self._thread.start()

    def _cleanup_objects(self):
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _on_worker_finished(self, result):
        self.finished.emit(result)

    def _on_worker_error(self, step: str, summary: str, detail: str):
        self.error_occurred.emit(step, summary, detail)

    def _on_thread_finished(self):
        self._is_running = False
        self.log_output.emit("[TaskRunner] Thread finished")
        self._cleanup_objects()

    def cancel(self):
        if not self._is_running:
            return
        self.log_output.emit("[TaskRunner] Stop requested...")
        try:
            self.r_bridge.cancel()
        except Exception as exc:
            self.log_output.emit(f"[TaskRunner] Stop: {exc}")

    def wait_for_completion(self, timeout_ms: int = 60000):
        thread = self._thread
        if thread is None:
            return True
        return thread.wait(timeout_ms)
