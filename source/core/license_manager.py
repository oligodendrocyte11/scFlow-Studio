from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import getpass
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.runtime_paths import get_license_dir, get_public_key_path, get_resource_path


PRODUCT_NAME = "scflow-studio"
LICENSE_SCOPE = "product_line"
APP_SALT = "scflow-studio|offline-license|2026-03"
FALLBACK_PERMANENT_DATE = "2099-12-31"
LICENSE_FILE_NAME = "license.json"
TRIAL_CONFIG_FILE_NAME = "trial_config.json"
DEFAULT_ACADEMIC_TRIAL_EXPIRED_MESSAGE = (
    "This academic trial version expired on 2026-10-01. "
    "Please contact the authors for an updated version."
)


@dataclass
class LicenseStatus:
    valid: bool
    message: str
    device_code: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    activation_code: str = ""
    expired: bool = False


class LicenseManager:
    def __init__(self):
        self.license_path = get_license_dir().joinpath(LICENSE_FILE_NAME)
        self._device_code = self._compute_device_code()
        self.trial_config = self._load_trial_config()

    def get_device_code(self) -> str:
        return self._device_code

    def is_academic_trial(self) -> bool:
        return bool(self.trial_config.get("trial_mode"))

    def _load_trial_config(self) -> dict[str, Any]:
        config_path = get_resource_path(TRIAL_CONFIG_FILE_NAME)
        if not config_path.is_file():
            return {}
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(config, dict):
            return {}
        return config

    def _trial_expiration_date(self) -> date | None:
        expires_at = str(self.trial_config.get("expires_on") or "").strip()
        if not expires_at:
            return None
        try:
            return date.fromisoformat(expires_at)
        except ValueError:
            return None

    def trial_status(self) -> LicenseStatus:
        expires_on = self._trial_expiration_date()
        configured_message = str(self.trial_config.get("expired_message") or "").strip()
        expired_message = configured_message or DEFAULT_ACADEMIC_TRIAL_EXPIRED_MESSAGE
        payload = {
            "product": PRODUCT_NAME,
            "license_scope": "academic_trial",
            "trial_mode": True,
            "expires_at": expires_on.isoformat() if expires_on else "",
        }
        if expires_on is None:
            return LicenseStatus(
                False,
                "The academic trial configuration is invalid. Please contact the authors for an updated version.",
                self.get_device_code(),
                payload=payload,
                expired=True,
            )
        if date.today() > expires_on:
            return LicenseStatus(
                False,
                expired_message,
                self.get_device_code(),
                payload=payload,
                expired=True,
            )
        return LicenseStatus(
            True,
            f"Academic Trial Version. Valid until {expires_on.isoformat()}.",
            self.get_device_code(),
            payload=payload,
        )

    def _compute_device_code(self) -> str:
        username = self._normalized_username()
        sid = self._get_windows_sid() if os.name == "nt" else ""
        raw = f"{LICENSE_SCOPE}|{username}|{sid}|{APP_SALT}"
        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        encoded = base64.b32encode(digest).decode("ascii").rstrip("=")
        short_code = encoded[:25]
        return "-".join(short_code[i:i + 5] for i in range(0, len(short_code), 5))

    def load_saved_license(self) -> LicenseStatus:
        if self.is_academic_trial():
            return self.trial_status()

        if not self.license_path.is_file():
            return LicenseStatus(False, "No local license was detected. Please activate the software first.", self.get_device_code())

        try:
            saved = json.loads(self.license_path.read_text(encoding="utf-8"))
        except Exception:
            self.clear_invalid_license()
            return LicenseStatus(False, "The local license file is corrupted. Please enter the activation code again.", self.get_device_code())

        activation_code = (saved.get("activation_code") or "").strip()
        if not activation_code:
            self.clear_invalid_license()
            return LicenseStatus(False, "The local license file does not contain an activation code. Please activate again.", self.get_device_code())

        status = self._validate_activation_code(activation_code)
        if not status.valid:
            self.clear_invalid_license()
            return status

        try:
            saved["last_verified_at"] = datetime.now().replace(microsecond=0).isoformat()
            self.license_path.write_text(
                json.dumps(saved, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
        return status

    def activate_from_code(self, code: str) -> LicenseStatus:
        status = self._validate_activation_code(code)
        if not status.valid:
            return status

        payload = status.payload
        self.license_path.parent.mkdir(parents=True, exist_ok=True)
        saved = {
            "product": payload["product"],
            "device_code": payload["device_code"],
            "activation_code": status.activation_code,
            "activated_at": datetime.now().replace(microsecond=0).isoformat(),
            "last_verified_at": datetime.now().replace(microsecond=0).isoformat(),
        }
        try:
            self.license_path.write_text(
                json.dumps(saved, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            return LicenseStatus(
                False,
                f"License validation passed, but saving the local license file failed: {exc}",
                self.get_device_code(),
                payload=payload,
                activation_code=status.activation_code,
            )

        return LicenseStatus(
            True,
            f"Activation succeeded. Valid until {payload['expires_at']}.",
            self.get_device_code(),
            payload=payload,
            activation_code=status.activation_code,
        )

    def clear_invalid_license(self) -> None:
        try:
            if self.license_path.exists():
                self.license_path.unlink()
        except Exception:
            pass

    def build_license_payload(
        self,
        device_code: str,
        expires_at: str,
        issuer: str = "offline-admin",
        issued_at: str | None = None,
        license_id: str | None = None,
    ) -> dict[str, str]:
        issued_at = issued_at or date.today().isoformat()
        license_id = license_id or self.generate_license_id()
        return {
            "product": PRODUCT_NAME,
            "license_scope": LICENSE_SCOPE,
            "device_code": self.normalize_device_code(device_code),
            "expires_at": expires_at or FALLBACK_PERMANENT_DATE,
            "issued_at": issued_at,
            "license_id": license_id,
            "issuer": issuer or "offline-admin",
        }

    @staticmethod
    def generate_license_id() -> str:
        return f"LIC-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    @staticmethod
    def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @staticmethod
    def normalize_device_code(device_code: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", (device_code or "")).upper()
        if not cleaned:
            return ""
        return "-".join(cleaned[i:i + 5] for i in range(0, len(cleaned), 5))

    def _validate_activation_code(self, code: str) -> LicenseStatus:
        device_code = self.get_device_code()
        normalized_code = self._normalize_activation_code(code)
        if not normalized_code:
            return LicenseStatus(False, "Please enter an activation code.", device_code)

        cryptography_error = self._ensure_crypto_available()
        if cryptography_error:
            return LicenseStatus(False, cryptography_error, device_code, activation_code=normalized_code)

        try:
            envelope = self._decode_activation_code(normalized_code)
        except ValueError as exc:
            return LicenseStatus(False, str(exc), device_code, activation_code=normalized_code)

        payload = envelope.get("payload")
        signature_text = envelope.get("signature")
        if not isinstance(payload, dict) or not isinstance(signature_text, str):
            return LicenseStatus(False, "The activation code is incomplete. Please make sure it was copied completely.", device_code, activation_code=normalized_code)

        required_fields = {
            "product",
            "license_scope",
            "device_code",
            "expires_at",
            "issued_at",
            "license_id",
            "issuer",
        }
        missing = [field for field in required_fields if field not in payload]
        if missing:
            return LicenseStatus(False, f"The activation code is missing required fields: {', '.join(missing)}.", device_code, activation_code=normalized_code)

        if payload.get("product") != PRODUCT_NAME:
            return LicenseStatus(False, "This activation code does not belong to this product.", device_code, payload=payload, activation_code=normalized_code)
        if payload.get("license_scope") != LICENSE_SCOPE:
            return LicenseStatus(False, "This activation scope is not supported.", device_code, payload=payload, activation_code=normalized_code)

        target_device = self.normalize_device_code(str(payload.get("device_code", "")))
        if target_device != self.normalize_device_code(device_code):
            return LicenseStatus(False, "This activation code does not match the current device code.", device_code, payload=payload, activation_code=normalized_code)

        try:
            expires_on = date.fromisoformat(str(payload.get("expires_at", "")))
        except ValueError:
            return LicenseStatus(False, "The expiration date in the activation code is invalid.", device_code, payload=payload, activation_code=normalized_code)

        signature_bytes = self._urlsafe_b64decode(signature_text)
        if not signature_bytes:
            return LicenseStatus(False, "The activation-code signature is missing or malformed.", device_code, payload=payload, activation_code=normalized_code)

        verify_error = self._verify_signature(payload, signature_bytes)
        if verify_error:
            return LicenseStatus(False, verify_error, device_code, payload=payload, activation_code=normalized_code)

        if expires_on < date.today():
            return LicenseStatus(False, f"The activation code has expired: {expires_on.isoformat()}.", device_code, payload=payload, activation_code=normalized_code, expired=True)

        return LicenseStatus(
            True,
            f"License is valid until {expires_on.isoformat()}.",
            device_code,
            payload=payload,
            activation_code=normalized_code,
        )

    @staticmethod
    def _normalize_activation_code(code: str) -> str:
        return re.sub(r"\s+", "", code or "")

    def _decode_activation_code(self, code: str) -> dict[str, Any]:
        try:
            decoded = self._urlsafe_b64decode(code)
            if not decoded:
                raise ValueError
            data = json.loads(decoded.decode("utf-8"))
        except Exception as exc:
            raise ValueError("The activation-code format is invalid. Please make sure it was copied completely.") from exc
        if not isinstance(data, dict):
            raise ValueError("The activation-code format is invalid. Please make sure it was copied completely.")
        return data

    @staticmethod
    def _urlsafe_b64decode(value: str) -> bytes:
        if not value:
            return b""
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)

    @staticmethod
    def _urlsafe_b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    def _verify_signature(self, payload: dict[str, Any], signature: bytes) -> str:
        try:
            public_key = self._load_public_key()
            public_key.verify(signature, self.canonical_payload_bytes(payload))
        except FileNotFoundError:
            return "The license public key was not found. Please reinstall the software."
        except Exception as exc:
            if exc.__class__.__name__ == "InvalidSignature":
                return "Activation-code validation failed. The code may have been modified."
            return f"License validation failed: {exc}"
        return ""

    def _load_public_key(self):
        from cryptography.hazmat.primitives import serialization

        public_key_path = get_public_key_path()
        if not public_key_path.is_file():
            raise FileNotFoundError(str(public_key_path))
        pem = public_key_path.read_bytes()
        return serialization.load_pem_public_key(pem)

    @staticmethod
    def _ensure_crypto_available() -> str:
        try:
            import cryptography  # noqa: F401
        except Exception:
            return "The cryptography dependency is missing. Please install the dependencies listed in requirements.txt."
        return ""

    @staticmethod
    def _normalized_username() -> str:
        username = getpass.getuser() or os.environ.get("USERNAME") or "unknown-user"
        return username.strip().casefold()

    @staticmethod
    def _get_windows_sid() -> str:
        if os.name != "nt":
            return ""
        sid_value = ""
        try:
            advapi32 = ctypes.windll.advapi32
            kernel32 = ctypes.windll.kernel32

            TOKEN_QUERY = 0x0008
            TokenUser = 1

            token = ctypes.wintypes.HANDLE()
            current_process = kernel32.GetCurrentProcess()
            if not advapi32.OpenProcessToken(current_process, TOKEN_QUERY, ctypes.byref(token)):
                raise OSError("OpenProcessToken failed")

            try:
                needed = ctypes.wintypes.DWORD(0)
                advapi32.GetTokenInformation(token, TokenUser, None, 0, ctypes.byref(needed))
                buffer = ctypes.create_string_buffer(needed.value)
                if not advapi32.GetTokenInformation(token, TokenUser, buffer, needed, ctypes.byref(needed)):
                    raise OSError("GetTokenInformation failed")

                sid_ptr = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
                sid_string = ctypes.wintypes.LPWSTR()
                if not advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid_ptr), ctypes.byref(sid_string)):
                    raise OSError("ConvertSidToStringSidW failed")
                try:
                    sid_value = sid_string.value or ""
                finally:
                    kernel32.LocalFree(sid_string)
            finally:
                kernel32.CloseHandle(token)
        except Exception:
            pass

        return sid_value


def encode_activation_envelope(payload: dict[str, Any], signature: bytes) -> str:
    envelope = {
        "payload": payload,
        "signature": LicenseManager._urlsafe_b64encode(signature),
    }
    raw = json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return LicenseManager._urlsafe_b64encode(raw)
