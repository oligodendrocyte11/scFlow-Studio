"""
RBridge — subprocess Rscript 
"""
import os
import re
import json
import shutil
import subprocess
import tempfile
from typing import Optional, Callable
from dataclasses import dataclass

SUBPROCESS_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class RResult:
    """R Results"""
    success: bool
    summary: dict
    output_dir: str
    figures: list
    tables: list
    output_rds: str = ""
    error_message: str = ""


class RBridge:
    """
    Python → R.

    :
    1. Python Parameters params.json
    2. subprocess Rscript xxx.R params.json
    3. R: result.rds + summary.json + PNG/PDF
    4. Python Load summary.json Results
    """

    def __init__(self, r_executable: str = "Rscript", scripts_dir: str = ""):
        self.r_exec = r_executable
        self.scripts_dir = scripts_dir
        self._runtime_root = self._ensure_runtime_root()
        self._safe_scripts_dir = ""
        self._safe_r_exec = ""

    @staticmethod
    def _is_ascii_path(path: str) -> bool:
        try:
            path.encode("ascii")
            return True
        except UnicodeEncodeError:
            return False

    def _ensure_runtime_root(self) -> str:
        if os.name != "nt":
            fallback = os.path.join(tempfile.gettempdir(), "scflow_runtime")
            os.makedirs(fallback, exist_ok=True)
            return fallback

        candidates = []
        temp_root = tempfile.gettempdir()
        if self._is_ascii_path(temp_root):
            candidates.append(os.path.join(temp_root, "scflow_runtime"))
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata and self._is_ascii_path(local_appdata):
            candidates.append(os.path.join(local_appdata, "scflow_runtime"))
        public_root = os.environ.get("PUBLIC", r"C:\Users\Public")
        candidates.append(os.path.join(public_root, "scflow_runtime"))
        candidates.append(os.path.join(os.environ.get("SystemDrive", "C:"), "scflow_runtime"))

        for candidate in candidates:
            if not self._is_ascii_path(candidate):
                continue
            try:
                os.makedirs(candidate, exist_ok=True)
                return candidate
            except OSError:
                continue

        fallback = os.path.join(tempfile.gettempdir(), "scflow_runtime")
        os.makedirs(fallback, exist_ok=True)
        return fallback

    def create_safe_runtime_dir(self, name: str) -> str:
        safe_name = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in name).strip("._")
        if not safe_name:
            safe_name = "task"
        path = os.path.join(self._runtime_root, safe_name)
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except OSError:
            fallback_root = os.path.join(tempfile.gettempdir(), "scflow_runtime")
            os.makedirs(fallback_root, exist_ok=True)
            self._runtime_root = fallback_root
            path = os.path.join(self._runtime_root, safe_name)
            os.makedirs(path, exist_ok=True)
            return path

    def _sync_safe_scripts_dir(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self.scripts_dir:
            return ""
        target = os.path.join(self._runtime_root, "r_scripts_runtime")
        os.makedirs(self._runtime_root, exist_ok=True)
        if log_callback:
            log_callback("[RBridge] Preparing safe script workspace...")
        shutil.copytree(self.scripts_dir, target, dirs_exist_ok=True)
        self._safe_scripts_dir = target
        return target

    def _compute_r_portable_signature(self, root: str) -> str:
        probe_paths = [
            os.path.join(root, "bin", "Rscript.exe"),
            os.path.join(root, "library"),
            os.path.join(root, "etc"),
        ]
        parts = [os.path.abspath(root)]
        for probe in probe_paths:
            if os.path.exists(probe):
                stat = os.stat(probe)
                parts.append(f"{probe}:{int(stat.st_mtime)}:{stat.st_size}")
        return "|".join(parts)

    def _sync_safe_r_portable(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self.r_exec:
            return self.r_exec

        if os.name != "nt":
            return os.path.abspath(self.r_exec).replace("\\", "/")

        source_exec = os.path.abspath(self.r_exec)
        if self._is_ascii_path(source_exec):
            return source_exec.replace("\\", "/")

        source_root = os.path.dirname(os.path.dirname(source_exec))
        target_root = os.path.join(self._runtime_root, "R-portable-runtime")
        target_exec = os.path.join(target_root, "bin", "Rscript.exe")
        marker_path = os.path.join(target_root, ".source_signature")
        source_signature = self._compute_r_portable_signature(source_root)

        need_refresh = True
        if os.path.isfile(target_exec) and os.path.isfile(marker_path):
            try:
                with open(marker_path, "r", encoding="utf-8") as handle:
                    need_refresh = handle.read().strip() != source_signature
            except OSError:
                need_refresh = True

        if need_refresh:
            if log_callback:
                log_callback("[RBridge] Preparing safe R runtime (may take a while on first run)...")
            if os.path.isdir(target_root):
                shutil.rmtree(target_root, ignore_errors=True)
            shutil.copytree(source_root, target_root)
            with open(marker_path, "w", encoding="utf-8") as handle:
                handle.write(source_signature)
        elif log_callback:
            log_callback("[RBridge] Reusing safe R runtime.")

        self._safe_r_exec = target_exec
        return target_exec.replace("\\", "/")

    def _resolve_runtime_r_exec(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        safe_exec = self._sync_safe_r_portable(log_callback=log_callback)
        if os.name != "nt":
            return safe_exec.replace("\\", "/")
        short_path = self._to_windows_short_path(safe_exec.replace("/", "\\"))
        if short_path and os.path.exists(short_path):
            return short_path.replace("\\", "/")
        return safe_exec.replace("\\", "/")

    def to_runtime_safe_existing_path(self, path: str) -> str:
        if not path:
            return path
        abs_path = os.path.abspath(path)
        short_path = self._to_windows_short_path(abs_path)
        if short_path and os.path.exists(short_path):
            return short_path.replace("\\", "/")
        return abs_path.replace("\\", "/")

    @staticmethod
    def _to_windows_short_path(path: str) -> str:
        if os.name != "nt":
            return path
        try:
            import ctypes
            buffer_size = 4096
            output = ctypes.create_unicode_buffer(buffer_size)
            result = ctypes.windll.kernel32.GetShortPathNameW(path, output, buffer_size)
            if result and output.value:
                return output.value
        except Exception:
            pass
        return ""


    @staticmethod
    def _normalize_r_output_line(line: str) -> str:
        """Translate common non-English R warning fragments when locale fallback is unavailable."""
        zh_warning_messages = "\u8b66\u544a\u4fe1\u606f:"
        zh_warning_colon = "\u8b66\u544a:"
        zh_warning = "\u8b66\u544a"
        zh_package = "\u7a0b\u5e8f\u5305"
        zh_built = "\u662f\u7528R\u7248\u672c"
        zh_built_tail = "\u6765\u5efa\u9020\u7684"
        zh_missing_arg = "\u7f3a\u5c11\u53c2\u6570"
        zh_missing_default = "\u4e5f\u7f3a\u5931\u9ed8\u8ba4\u503c"
        replacements = {
            zh_warning_messages: "Warning messages:",
            zh_warning_colon: "Warning:",
            zh_warning: "Warning",
            zh_package: "package",
            zh_built: "was built under R version",
            zh_built_tail: "",
            zh_missing_arg: "missing argument",
            zh_missing_default: "with no default",
        }
        out = line
        package_pattern = zh_package + r"[‘']([^’']+)[’']" + zh_built + r"([^ ]+) " + zh_built_tail
        out = re.sub(package_pattern, r"package '\1' was built under R version \2", out)
        for old, new in replacements.items():
            out = out.replace(old, new)
        return out

    def call_script(
        self,
        script_name: str,
        params: dict,
        output_dir: str,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> RResult:
        """
        R.

        Args:
            script_name: R file("02_qc.R")
            params: Parameters, params.json
            output_dir: R 
            log_callback: Log fn(line: str)
            progress_callback: fn(percent: int, message: str)

        Returns:
            RResult
        """
        os.makedirs(output_dir, exist_ok=True)

        safe_scripts_dir = self._sync_safe_scripts_dir(log_callback=log_callback) if self.scripts_dir else self.scripts_dir
        run_dir = self.create_safe_runtime_dir(os.path.splitext(script_name)[0])
        if log_callback:
            log_callback(f"[RBridge] Creating safe run directory: {run_dir}")

        # Parameter file
        params_path = os.path.join(run_dir, "params.json")
        if log_callback:
            log_callback(f"[RBridge] Writing params file: {params_path}")
        params["output_dir"] = output_dir.replace("\\", "/")
        with open(params_path, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=2, ensure_ascii=False)

        # 
        script_path = os.path.join(safe_scripts_dir, script_name)
        if not os.path.isfile(script_path):
            return RResult(
                success=False, summary={}, output_dir=output_dir,
                figures=[], tables=[],
                error_message=f"R script not found: {script_path}"
            )

        r_exec = self._resolve_runtime_r_exec(log_callback=log_callback)
        cmd = [r_exec, "--vanilla", script_path.replace("\\", "/"), params_path.replace("\\", "/")]

        if log_callback:
            log_callback(f"[RBridge] Running: {' '.join(cmd)}")

        # 
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=safe_scripts_dir,
                creationflags=SUBPROCESS_NO_WINDOW,
            )
            self._current_process = process

            # Load
            for line in iter(process.stdout.readline, ""):
                line = self._normalize_r_output_line(line.rstrip())
                if line:
                    if log_callback:
                        log_callback(line)
                    # (R ##PROGRESS:50:)
                    if line.startswith("##PROGRESS:"):
                        parts = line.split(":", 2)
                        if len(parts) >= 3 and progress_callback:
                            try:
                                pct = int(parts[1])
                                msg = parts[2]
                                progress_callback(pct, msg)
                            except ValueError:
                                pass

            process.wait()
            self._current_process = None

            if process.returncode != 0:
                # Load summary.json Error
                summary = self._read_summary(output_dir)
                return RResult(
                    success=False,
                    summary=summary,
                    output_dir=output_dir,
                    figures=[],
                    tables=[],
                    error_message=summary.get("message", f"R exit: {process.returncode}")
                )

            # Success: load summary.json
            summary = self._read_summary(output_dir)

            # jsonlite auto_unbox 
            # figures/tables list
            figures = summary.get("figures", [])
            if isinstance(figures, str):
                figures = [figures]
            tables = summary.get("tables", [])
            if isinstance(tables, str):
                tables = [tables]
            output_rds = summary.get("output_rds", "")

            return RResult(
                success=True,
                summary=summary,
                output_dir=output_dir,
                figures=[os.path.join(output_dir, f) for f in figures],
                tables=[os.path.join(output_dir, t) for t in tables],
                output_rds=os.path.join(output_dir, output_rds) if output_rds else "",
            )

        except FileNotFoundError:
            return RResult(
                success=False, summary={}, output_dir=output_dir,
                figures=[], tables=[],
                error_message=f"Cannot find Rscript: {r_exec}\nPlease configure the R path in Settings."
            )
        except Exception as e:
            return RResult(
                success=False, summary={}, output_dir=output_dir,
                figures=[], tables=[],
                error_message=str(e)
            )

    def cancel(self):
        """ R """
        proc = getattr(self, "_current_process", None)
        if proc and proc.poll() is None:
            proc.terminate()

    def check_environment(self, output_dir: str) -> dict:
        """ R Case"""
        result = self.call_script("00_check_env.R", {}, output_dir)
        return result.summary

    def _read_summary(self, output_dir: str) -> dict:
        summary_path = os.path.join(output_dir, "summary.json")
        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
