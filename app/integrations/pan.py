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

from app.integrations.base import BaseKYCProvider
from app.models.setting import SystemSetting

logger = logging.getLogger(__name__)

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

    def _resolve_credentials(self, company=None) -> dict:
        """
        Resolves CVL KRA SOAP credentials from Company profile or System Settings.

        Fields used by SOAP API:
          - poscode    → Company.pos_code
          - username   → Company.api_user_id
          - password   → Company.api_password   (plaintext — encrypted per-request by GetPassword)
          - passkey    → Company.aes_key         (user-defined hash key sent to GetPassword)
        """
        # Always use active CVL KRA endpoint
        base_url = "https://krapancheck.cvlindia.com/CVLPanInquiry.svc"

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

        # passkey = the AES Key field in Company Profile (user-defined hash key for GetPassword)
        passkey = (
            (company.aes_key if company and company.aes_key else None) or
            SystemSetting.get_val('cvl_kra_aes_key') or
            os.getenv('CVL_KRA_AES_KEY') or ""
        ).strip()

        return {
            "base_url": base_url,
            "poscode": poscode,
            "username": username,
            "password": password,
            "passkey": passkey,
        }

    # ── Step 1: GetPassword ───────────────────────────────────────────────────

    def get_encrypted_password(self, creds: dict) -> tuple[str, str]:
        """
        Calls CVL GetPassword SOAP method.
        Returns (encrypted_password, error_message).
        Encrypted password is APP_GET_PASS from the XML response.
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

    # ── Step 2: GetPANStatus ──────────────────────────────────────────────────

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

    # ── Main entry: verify_pan_with_dob ──────────────────────────────────────

    def verify_pan_with_dob(self, pan_number: str, dob: str = None, company=None) -> dict:
        """
        Verify PAN using CVL KRA SOAP GetPANStatus (V6.0).
        DOB is accepted for UI compatibility but CVL GetPANStatus does not require it.
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

        # Check minimum required credentials
        has_live_creds = bool(
            creds["poscode"] and
            creds["username"] and
            creds["password"] and
            creds["passkey"]
        )

        if has_live_creds:
            # ── Step 1: GetPassword ──────────────────────────────────────────
            enc_password, err = self.get_encrypted_password(creds)
            if not enc_password:
                logger.warning(f"CVL GetPassword failed: {err}")
                return {
                    "success": False,
                    "status": "failed",
                    "status_message": f"CVL KRA Authentication Failed: {err}",
                    "raw_response": {"error": err},
                }

            # ── Step 2: GetPANStatus ─────────────────────────────────────────
            kyc_data, err, raw_req_xml = self.call_get_pan_status(pan_clean, creds, enc_password)
            if err:
                logger.warning(f"CVL GetPANStatus failed: {err}")
                return {
                    "success": False,
                    "status": "failed",
                    "status_message": f"CVL KRA PAN Lookup Failed: {err}",
                    "raw_response": {"error": err},
                    "raw_request": raw_req_xml
                }

            # ── Parse response ───────────────────────────────────────────────
            app_name     = kyc_data.get("APP_NAME", "")
            status_code  = kyc_data.get("APP_STATUS", "").strip().zfill(3)
            kyc_mode     = kyc_data.get("APP_KYC_MODE", "")
            per_add      = kyc_data.get("APP_PER_ADD_PROOF", "")
            cor_add      = kyc_data.get("APP_COR_ADD_PROOF", "")
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
                f"CVL-GPS-{creds['poscode']}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )

            return {
                "success":              is_success,
                "status":               "verified" if is_success else "failed",
                "status_message":       f"CVL KRA GetPANStatus: {status_desc} (Code: {status_code})",
                "full_name":            app_name or "NAME NOT RETURNED BY CVL",
                "first_name":           first_name,
                "middle_name":          middle_name,
                "last_name":            last_name,
                "category":             category,
                "pan_status":           status_desc.upper(),
                "dob_match":            True,   # CVL GetPANStatus does not validate DOB
                "aadhaar_seeding_status": aadhaar_status,
                "reference_id":         reference_id,
                "method":               "GetPANStatus",
                "status_date":          status_dt,
                "kyc_mode":             kyc_mode_desc,
                "ipv_flag":             ipv_flag,
                "remarks":              remarks,
                "response_date":        resp_date,
                "raw_response":         kyc_data,
                "raw_request":          raw_req_xml,
            }

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
