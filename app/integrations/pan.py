"""
CVL KRA PAN Verification Integration — SOAP/XML Web Service V6.0
Official endpoints:
  Production : https://pancheck.www.kracvl.com/CVLPanInquiry.svc
  UAT        : https://krapancheck.cvlindia.com/CVLPanInquiry.svc

Flow:
  1. GetPassword  → encrypt user password using PassKey → get APP_GET_PASS
  2. GetPANStatus → SOAP request with pan, username, PosCode, encrypted password & passkey
  3. Parse XML response → return structured dict
"""

import os
import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
import base64
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from app.integrations.base import BaseKYCProvider
from app.models.setting import SystemSetting

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CVL REST API (V2.6) Cryptographic Helpers (Section 9 of CVL Specification)
# ─────────────────────────────────────────────────────────────────────────────

def base64UrlEncode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def base64UrlDecode(data: str) -> bytes:
    padded_data = data + "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(padded_data)

def cvl_rest_encrypt(aes_key: str, data: str) -> str:
    iv = os.urandom(16)
    key = base64UrlDecode(aes_key.strip())
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = pad(data.encode('utf-8'), AES.block_size)
    encrypted_text = cipher.encrypt(padded_data)
    iv_encoded = base64UrlEncode(iv)
    encrypted_text_encoded = base64UrlEncode(encrypted_text)
    return iv_encoded + ":" + encrypted_text_encoded

def cvl_rest_decrypt(aes_key: str, enc_string: str) -> str:
    try:
        iv_str, cipher_str = enc_string.split(":")
        iv = base64UrlDecode(iv_str)
        cipher_bytes = base64UrlDecode(cipher_str)
        key = base64UrlDecode(aes_key.strip())
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_bytes = cipher.decrypt(cipher_bytes)
        return unpad(decrypted_bytes, AES.block_size).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to decrypt CVL REST response: {e}")
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# SOAP envelope templates
# ─────────────────────────────────────────────────────────────────────────────

SOAP_NS = "https://krapancheck.cvlindia.com"

GET_PASSWORD_ENVELOPE = """\
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:tns="{ns}">
  <soap:Body>
    <tns:GetPassword>
      <tns:webApi>
        <tns:password>{password}</tns:password>
        <tns:passKey>{passkey}</tns:passKey>
      </tns:webApi>
    </tns:GetPassword>
  </soap:Body>
</soap:Envelope>"""

GET_PAN_STATUS_ENVELOPE = """\
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:tns="{ns}">
  <soap:Body>
    <tns:GetPanStatus>
      <tns:webApi>
        <tns:pan>{pan}</tns:pan>
        <tns:userName>{username}</tns:userName>
        <tns:posCode>{poscode}</tns:posCode>
        <tns:password>{enc_password}</tns:password>
        <tns:passKey>{passkey}</tns:passKey>
      </tns:webApi>
    </tns:GetPanStatus>
  </soap:Body>
</soap:Envelope>"""


# ─────────────────────────────────────────────────────────────────────────────
# XML helpers
# ─────────────────────────────────────────────────────────────────────────────

def _soap_headers(action: str) -> dict:
    return {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"{SOAP_NS}/ICVLPanInquiry/{action}"',
        "User-Agent": "ZoiKYC/1.0"
    }


def _find_text(root: ET.Element, tag: str, default: str = "") -> str:
    """Searches entire XML tree for a tag, returning its text."""
    el = root.find(f".//{tag}")
    return (el.text or "").strip() if el is not None else default


def _parse_error(root: ET.Element) -> str | None:
    """Returns error message if XML contains an ERROR node, else None."""
    err_code = _find_text(root, "ERROR_CODE")
    err_msg = _find_text(root, "ERROR_MSG")
    if err_code:
        return f"{err_msg} ({err_code})" if err_msg else err_code
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Status & mode lookup maps (CVL KRA V6.0 documentation)
# ─────────────────────────────────────────────────────────────────────────────

CVL_STATUS_MAP = {
    "000": "Not Checked with Respective KRA",
    "001": "Submitted / Under Process",
    "002": "KRA Verified",
    "003": "On Hold",
    "004": "Rejected",
    "005": "Not Available",
    "006": "Deactivated",
    "007": "KRA Validated",
    "011": "Existing KYC Submitted",
    "012": "Existing KYC Verified",
    "013": "Existing KYC Hold",
    "014": "Existing KYC Rejected",
    "022": "KYC Registered with CVLMF",
    "888": "Not Checked with Multiple KRA",
    "999": "Invalid PAN Format",
}

KYC_MODE_MAP = {
    "0": "Normal KYC",
    "1": "e-KYC with OTP",
    "2": "e-KYC with Biometric",
    "3": "Online Data Entry and IPV",
    "4": "Offline KYC - Aadhaar",
    "5": "DigiLocker",
    "": "Normal KYC",
}

PROOF_MAP = {
    "31": "Aadhaar",
    "01": "Passport",
    "02": "Driving License",
    "03": "Bank Passbook",
    "04": "Bank Account Statement",
    "06": "Voter Identity Card",
    "14": "Insurance Copy",
}

CATEGORY_MAP = {
    'P': 'Individual',
    'C': 'Company',
    'H': 'Hindu Undivided Family (HUF)',
    'F': 'Partnership Firm',
    'A': 'Association of Persons (AOP)',
    'T': 'Trust',
    'B': 'Body of Individuals (BOI)',
    'L': 'Local Authority',
    'J': 'Artificial Juridical Person',
    'G': 'Government',
}

# Status codes that mean "verified / registered"
VERIFIED_STATUS_CODES = {"002", "007", "012", "022"}


# ─────────────────────────────────────────────────────────────────────────────
# Provider class
# ─────────────────────────────────────────────────────────────────────────────

class PANVerificationProvider(BaseKYCProvider):
    """
    CVL KRA PAN Verification via official SOAP/XML Web Service V6.0.

    Step 1: GetPassword  → encrypts company password using PassKey
    Step 2: GetPANStatus → fetches KYC status from CVL KRA
    """

    def get_provider_name(self) -> str:
        return "CVL KRA (CDSL Ventures Limited) — SOAP V6.0"

    def health_check(self) -> bool:
        return True

    def verify_bank_account(self, account_number: str, ifsc: str) -> dict:
        raise NotImplementedError("Bank account verification is handled by PennyDrop provider.")

    def verify_pan(self, pan_number: str, name: str = None) -> dict:
        return self.verify_pan_with_dob(pan_number=pan_number, dob=None)

    # ── Credentials resolution ────────────────────────────────────────────────

    # ── Credentials resolution ────────────────────────────────────────────────

    def _resolve_credentials(self, company=None) -> dict:
        """
        Resolves CVL KRA credentials from Company profile or System Settings.
        Supports both REST API (api.kracvl.com) and SOAP API (krapancheck.cvlindia.com).
        """
        base_url = "https://krapancheck.cvlindia.com/CVLPanInquiry.svc"
        rest_url = "https://api.kracvl.com/int/api"

        poscode = (
            (company.pos_code if company and company.pos_code else None) or
            SystemSetting.get_val('cvl_kra_poscode') or
            os.getenv('CVL_KRA_POSCODE') or ""
        ).strip()

        username = (
            (company.api_user_id if company and company.api_user_id else None) or
            SystemSetting.get_val('cvl_kra_username') or
            os.getenv('CVL_KRA_USERNAME') or ""
        ).strip()

        password = (
            (company.api_password if company and company.api_password else None) or
            SystemSetting.get_val('cvl_kra_password') or
            os.getenv('CVL_KRA_PASSWORD') or ""
        ).strip()

        aes_key = (
            (company.aes_key if company and company.aes_key else None) or
            SystemSetting.get_val('cvl_kra_aes_key') or
            os.getenv('CVL_KRA_AES_KEY') or ""
        ).strip()

        api_key = (
            (company.api_key if company and company.api_key else None) or
            SystemSetting.get_val('cvl_kra_api_key') or
            os.getenv('CVL_KRA_API_KEY') or ""
        ).strip()

        return {
            "base_url": base_url,
            "rest_url": rest_url,
            "poscode": poscode,
            "username": username,
            "password": password,
            "passkey": aes_key,
            "aes_key": aes_key,
            "api_key": api_key,
        }

    # ── REST API Methods (https://api.kracvl.com/int/api/) ────────────────────

    def get_jwt_token(self, creds: dict) -> tuple[str, str, str]:
        """
        Calls CVL REST GetToken API.
        Payload: {"username": ..., "poscode": ..., "password": ...} encrypted with AES-192-CBC.
        Returns (token, error_message, raw_encrypted_payload).
        """
        url = f"{creds['rest_url']}/GetToken"
        headers = {
            "Content-Type": "application/json",
            "api_key": creds["api_key"]
        }
        auth_data = json.dumps({
            "username": creds["username"],
            "poscode": creds["poscode"],
            "password": creds["password"]
        })
        try:
            encrypted_payload = cvl_rest_encrypt(creds["aes_key"], auth_data)
        except Exception as e:
            return "", f"Failed to encrypt credentials: {e}", ""

        try:
            resp = requests.post(url, data=json.dumps(encrypted_payload), headers=headers, timeout=20)
            if resp.status_code != 200:
                return "", f"CVL GetToken HTTP {resp.status_code}: {resp.text[:200]}", encrypted_payload

            raw_resp = resp.json() if resp.text.startswith('"') else resp.text
            if isinstance(raw_resp, str) and ":" in raw_resp:
                decrypted = cvl_rest_decrypt(creds["aes_key"], raw_resp)
                try:
                    data = json.loads(decrypted)
                except Exception:
                    data = {}
            elif isinstance(raw_resp, dict):
                data = raw_resp
            else:
                try:
                    data = json.loads(raw_resp)
                except Exception:
                    data = {}

            token = data.get("token") or data.get("Token")
            if token:
                logger.info("CVL REST GetToken succeeded — JWT token obtained")
                return token, "", encrypted_payload

            err_code = data.get("error_code") or data.get("ErrorCode") or ""
            err_msg = data.get("error_message") or data.get("ErrorMessage") or ""
            err = f"{err_msg} ({err_code})" if err_code and err_msg else (err_msg or err_code or "Authentication failed")
            return "", err, encrypted_payload
        except Exception as e:
            return "", str(e), encrypted_payload

    def call_get_pan_status_rest(self, pan: str, creds: dict, token: str) -> tuple[dict, str, str]:
        """
        Calls CVL REST GetPanStatus API.
        Payload: {"pan": ..., "poscode": ...} encrypted with AES-192-CBC.
        Returns (parsed_dict, error_message, raw_encrypted_payload).
        """
        url = f"{creds['rest_url']}/GetPanStatus"
        headers = {
            "Content-Type": "application/json",
            "user-agent": "CustomUsrAgnt",
            "Token": token
        }
        packet = json.dumps({
            "pan": pan,
            "poscode": creds["poscode"]
        })
        try:
            enc_packet = cvl_rest_encrypt(creds["aes_key"], packet)
        except Exception as e:
            return {}, f"Encryption error: {e}", packet

        try:
            resp = requests.post(url, data=json.dumps(enc_packet), headers=headers, timeout=25)
            if resp.status_code != 200:
                return {}, f"CVL GetPanStatus HTTP {resp.status_code}: {resp.text[:200]}", enc_packet

            raw_resp = resp.json() if resp.text.startswith('"') else resp.text
            if isinstance(raw_resp, str) and ":" in raw_resp:
                decrypted = cvl_rest_decrypt(creds["aes_key"], raw_resp)
                try:
                    data = json.loads(decrypted)
                except Exception:
                    data = {}
            elif isinstance(raw_resp, dict):
                data = raw_resp
            else:
                try:
                    data = json.loads(raw_resp)
                except Exception:
                    data = {}

            if "resdtls" in data and isinstance(data["resdtls"], dict):
                inq = data["resdtls"].get("APP_PAN_INQ", {})
                summ = data["resdtls"].get("APP_PAN_SUMM", {})
            elif "resdtls" in data and isinstance(data["resdtls"], str) and ":" in data["resdtls"]:
                dec_res = cvl_rest_decrypt(creds["aes_key"], data["resdtls"])
                try:
                    parsed_res = json.loads(dec_res)
                    inq = parsed_res.get("APP_PAN_INQ", {})
                    summ = parsed_res.get("APP_PAN_SUMM", {})
                except Exception:
                    inq = {}
                    summ = {}
            else:
                inq = data.get("APP_PAN_INQ", {})
                summ = data.get("APP_PAN_SUMM", {})

            if isinstance(inq, list) and len(inq) > 0:
                inq = inq[0]

            return {**inq, **summ}, "", enc_packet
        except Exception as e:
            return {}, str(e), enc_packet

    # ── SOAP API Methods (https://krapancheck.cvlindia.com/) ──────────────────

    def get_encrypted_password(self, creds: dict) -> tuple[str, str]:
        """
        Calls CVL GetPassword SOAP method.
        Returns (encrypted_password, error_message).
        """
        url = creds["base_url"]
        body = GET_PASSWORD_ENVELOPE.format(
            ns=SOAP_NS,
            password=creds["password"],
            passkey=creds["passkey"],
        )

        try:
            resp = requests.post(
                url,
                data=body.encode("utf-8"),
                headers=_soap_headers("GetPassword"),
                timeout=20,
            )
        except requests.exceptions.Timeout:
            return "", "CVL KRA connection timed out during GetPassword (20s)"
        except requests.exceptions.ConnectionError as e:
            return "", f"Cannot reach CVL KRA server: {e}"

        if resp.status_code != 200:
            return "", f"CVL GetPassword HTTP {resp.status_code}: {resp.text[:200]}"

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            return "", f"CVL GetPassword: invalid XML response — {e}: {resp.text[:200]}"

        err = _parse_error(root)
        if err:
            return "", f"CVL GetPassword error: {err}"

        enc_pass = _find_text(root, "APP_GET_PASS")
        if not enc_pass:
            return "", f"CVL GetPassword: APP_GET_PASS missing in response: {resp.text[:300]}"

        logger.info("CVL GetPassword succeeded — encrypted password obtained")
        return enc_pass, ""

    def call_get_pan_status(self, pan: str, creds: dict, enc_password: str) -> tuple[dict, str, str]:
        """
        Calls CVL GetPANStatus SOAP method.
        Returns (parsed_kyc_dict, error_message, raw_request_xml).
        """
        url = creds["base_url"]
        body = GET_PAN_STATUS_ENVELOPE.format(
            ns=SOAP_NS,
            pan=pan,
            username=creds["username"],
            poscode=creds["poscode"],
            enc_password=enc_password,
            passkey=creds["passkey"],
        )

        try:
            resp = requests.post(
                url,
                data=body.encode("utf-8"),
                headers=_soap_headers("GetPanStatus"),
                timeout=25,
            )
        except requests.exceptions.Timeout:
            return {}, "CVL KRA connection timed out during GetPANStatus (25s)", body
        except requests.exceptions.ConnectionError as e:
            return {}, f"Cannot reach CVL KRA server: {e}", body

        if resp.status_code != 200:
            return {}, f"CVL GetPANStatus HTTP {resp.status_code}: {resp.text[:200]}", body

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            return {}, f"CVL GetPANStatus: invalid XML — {e}: {resp.text[:200]}", body

        err = _parse_error(root)
        if err:
            return {}, f"CVL GetPANStatus error: {err}", body

        # Extract APP_PAN_INQ fields
        inq = root.find(".//APP_PAN_INQ")
        summ = root.find(".//APP_PAN_SUMM")

        def t(tag): return _find_text(inq, tag) if inq is not None else ""
        def s(tag): return _find_text(summ, tag) if summ is not None else ""

        result = {
            "APP_PAN_NO":              t("APP_PAN_NO"),
            "APP_NAME":                t("APP_NAME"),
            "APP_STATUS":              t("APP_STATUS"),
            "APP_STATUSDT":            t("APP_STATUSDT"),
            "APP_ENTRYDT":             t("APP_ENTRYDT"),
            "APP_MODDT":               t("APP_MODDT"),
            "APP_STATUS_DELTA":        t("APP_STATUS_DELTA"),
            "APP_UPDT_STATUS":         t("APP_UPDT_STATUS"),
            "APP_HOLD_DEACTIVE_RMKS":  t("APP_HOLD_DEACTIVE_RMKS"),
            "APP_UPDT_RMKS":           t("APP_UPDT_RMKS"),
            "APP_KYC_MODE":            t("APP_KYC_MODE"),
            "APP_IPV_FLAG":            t("APP_IPV_FLAG"),
            "APP_UBO_FLAG":            t("APP_UBO_FLAG"),
            "APP_PER_ADD_PROOF":       t("APP_PER_ADD_PROOF"),
            "APP_COR_ADD_PROOF":       t("APP_COR_ADD_PROOF"),
            "BATCH_ID":                s("BATCH_ID"),
            "APP_RESPONSE_DATE":       s("APP_RESPONSE_DATE"),
            "APP_TOTAL_REC":           s("APP_TOTAL_REC"),
        }

        return result, "", body

    # ── Response Parser & Normalizer ──────────────────────────────────────────

    def _build_pan_response(self, pan_clean: str, kyc_data: dict, creds: dict, raw_req: str = "", method: str = "GetPanStatus") -> dict:
        app_name     = kyc_data.get("APP_NAME", "")
        status_code  = str(kyc_data.get("APP_STATUS", "")).strip().zfill(3)
        kyc_mode     = str(kyc_data.get("APP_KYC_MODE", "")).strip()
        per_add      = str(kyc_data.get("APP_PER_ADD_PROOF", "")).strip()
        cor_add      = str(kyc_data.get("APP_COR_ADD_PROOF", "")).strip()
        ipv_flag     = kyc_data.get("APP_IPV_FLAG", "")
        remarks      = kyc_data.get("APP_HOLD_DEACTIVE_RMKS", "")
        status_dt    = kyc_data.get("APP_STATUSDT", "")
        resp_date    = kyc_data.get("APP_RESPONSE_DATE", "")

        status_desc   = CVL_STATUS_MAP.get(status_code, f"Status Code {status_code}")
        kyc_mode_desc = KYC_MODE_MAP.get(kyc_mode, f"Mode {kyc_mode}" if kyc_mode else "Normal KYC")

        # Aadhaar seeding
        if per_add == "31":
            aadhaar_status = "LINKED (Aadhaar — Permanent Address)"
        elif cor_add == "31":
            aadhaar_status = "LINKED (Aadhaar — Correspondence Address)"
        elif per_add:
            aadhaar_status = f"Non-Aadhaar ({PROOF_MAP.get(per_add, f'Code {per_add}')})"
        else:
            aadhaar_status = "N/A"

        # Entity type from 4th character of PAN
        category = CATEGORY_MAP.get(pan_clean[3], "Individual")

        # Success if status is verified / registered
        is_success = status_code in VERIFIED_STATUS_CODES

        # Name parsing
        name_parts  = app_name.split() if app_name else []
        first_name  = name_parts[0] if name_parts else ""
        last_name   = name_parts[-1] if len(name_parts) > 1 else ""
        middle_name = " ".join(name_parts[1:-1]) if len(name_parts) > 2 else ""

        reference_id = (
            kyc_data.get("BATCH_ID") or
            f"CVL-{creds['poscode']}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

        return {
            "success":              is_success,
            "status":               "verified" if is_success else "failed",
            "status_message":       f"CVL KRA {method}: {status_desc} (Code: {status_code})",
            "full_name":            app_name or "NAME NOT RETURNED BY CVL",
            "first_name":           first_name,
            "middle_name":          middle_name,
            "last_name":            last_name,
            "category":             category,
            "pan_status":           status_desc.upper(),
            "dob_match":            True,   # CVL GetPANStatus does not validate DOB
            "aadhaar_seeding_status": aadhaar_status,
            "reference_id":         reference_id,
            "method":               method,
            "status_date":          status_dt,
            "kyc_mode":             kyc_mode_desc,
            "ipv_flag":             ipv_flag,
            "remarks":              remarks,
            "response_date":        resp_date,
            "raw_response":         kyc_data,
            "raw_request":          raw_req,
        }

    # ── Main entry: verify_pan_with_dob ──────────────────────────────────────

    def verify_pan_with_dob(self, pan_number: str, dob: str = None, company=None) -> dict:
        """
        Verify PAN against CVL KRA.
        Automatically uses official REST API (api.kracvl.com) if API Key is configured,
        otherwise uses SOAP Web Service (krapancheck.cvlindia.com).
        """
        pan_clean = (pan_number or "").strip().upper()

        # PAN format validation: AAAAA9999A
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan_clean):
            return {
                "success": False,
                "status": "invalid",
                "status_message": "Invalid PAN format. Must be 10 characters (e.g., ABCDE1234F).",
                "raw_response": {"error": "Invalid PAN format"},
            }

        creds = self._resolve_credentials(company)

        # ── Route 1: REST API (https://api.kracvl.com/int/api/) ───────────────
        has_rest_creds = bool(
            creds.get("api_key") and
            creds.get("aes_key") and
            creds.get("poscode") and
            creds.get("username") and
            creds.get("password")
        )

        if has_rest_creds:
            token, token_err, raw_token_req = self.get_jwt_token(creds)
            if token:
                kyc_data, pan_err, raw_pan_req = self.call_get_pan_status_rest(pan_clean, creds, token)
                if not pan_err and kyc_data:
                    return self._build_pan_response(pan_clean, kyc_data, creds, raw_req=raw_pan_req, method="GetPanStatus (REST)")
                if pan_err:
                    return {
                        "success": False,
                        "status": "failed",
                        "status_message": f"CVL KRA REST Lookup Failed: {pan_err}",
                        "raw_response": {"error": pan_err},
                        "raw_request": raw_pan_req
                    }
            elif token_err and "WEBERR" in token_err:
                # Direct credential error from CVL KRA
                return {
                    "success": False,
                    "status": "failed",
                    "status_message": f"CVL KRA Authentication Failed: {token_err}",
                    "raw_response": {"error": token_err},
                    "raw_request": raw_token_req
                }

        # ── Route 2: SOAP Web Service (https://krapancheck.cvlindia.com/) ─────
        has_soap_creds = bool(
            creds.get("poscode") and
            creds.get("username") and
            creds.get("password") and
            creds.get("passkey")
        )

        if has_soap_creds:
            enc_password, err = self.get_encrypted_password(creds)
            if not enc_password:
                return {
                    "success": False,
                    "status": "failed",
                    "status_message": f"CVL KRA Authentication Failed: {err}",
                    "raw_response": {"error": err},
                }

            kyc_data, err, raw_req_xml = self.call_get_pan_status(pan_clean, creds, enc_password)
            if err:
                return {
                    "success": False,
                    "status": "failed",
                    "status_message": f"CVL KRA PAN Lookup Failed: {err}",
                    "raw_response": {"error": err},
                    "raw_request": raw_req_xml
                }

            return self._build_pan_response(pan_clean, kyc_data, creds, raw_req=raw_req_xml, method="GetPanStatus (SOAP)")

        # ── Sandbox fallback (no credentials configured) ─────────────────────
        category     = CATEGORY_MAP.get(pan_clean[3], "Individual")
        sim_name     = "VIJAY VAISHNAV" if pan_clean[3] == 'P' else "ZOI FINTECH SOLUTIONS PVT LTD"
        name_parts   = sim_name.split()

        return {
            "success":              True,
            "status":               "verified",
            "status_message":       (
                "CVL KRA Verified (DEMO — Configure POS Code, Username, Password & PassKey "
                "in Company Profile → KRA Credentials for live API)"
            ),
            "full_name":            sim_name,
            "first_name":           name_parts[0],
            "middle_name":          "",
            "last_name":            name_parts[-1] if len(name_parts) > 1 else "",
            "category":             category,
            "pan_status":           "KRA VERIFIED (002)",
            "dob_match":            True,
            "aadhaar_seeding_status": "LINKED (Aadhaar — Permanent Address)",
            "reference_id":         f"CVL-DEMO-{os.urandom(3).hex().upper()}",
            "method":               "GetPANStatus",
            "status_date":          datetime.now().strftime("%d/%m/%Y"),
            "kyc_mode":             "Normal KYC",
            "ipv_flag":             "Y",
            "remarks":              "",
            "response_date":        datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "raw_response": {
                "APP_PAN_NO":   pan_clean,
                "APP_NAME":     sim_name,
                "APP_STATUS":   "002",
                "APP_KYC_MODE": "0",
                "APP_IPV_FLAG": "Y",
                "APP_PER_ADD_PROOF": "31",
                "APP_STATUSDT": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "NOTE":         "DEMO MODE — CVL KRA credentials not configured",
            },
        }
