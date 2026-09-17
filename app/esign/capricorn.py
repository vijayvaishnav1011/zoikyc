import os
import re
import base64
import json
import logging
import random
import requests
from typing import Dict, Any, Optional
from app.integrations.base import BaseESignProvider

logger = logging.getLogger(__name__)


class CapricornESignProvider(BaseESignProvider):
    """
    Integration provider for Capricorn Identity Services E-Sign API (esign.network).
    Handles Base64 PDF transmission, online-aadhaar-otp signing, and signed document retrieval.
    """

    POST_JSON_URL = "https://www.esign.network/op/api/v1.0/postjson"
    POST_XML_URL = "https://www.esign.network/op/api/v1.0/postxml"
    DEFAULT_API_URL = POST_JSON_URL
    DEFAULT_TOKEN = "1D70678680F404BF92E4618FDF5D39A518D9F192"
    DEFAULT_KEY = "hLIc0TqVMt6aH4asHxpqlwloVZfL7raq8X8NSWu2OVCo$$$$$$shodIaK5g=="

    def __init__(self, api_url: Optional[str] = None, token: Optional[str] = None, key: Optional[str] = None):
        raw_url = api_url or os.environ.get('CAPRICORN_API_URL', self.DEFAULT_API_URL)
        if raw_url:
            raw_url = raw_url.replace("www..esign.network", "www.esign.network")
        self.api_url = raw_url
        self.token = token or os.environ.get('CAPRICORN_API_TOKEN', self.DEFAULT_TOKEN)
        self.key = key or os.environ.get('CAPRICORN_API_KEY', self.DEFAULT_KEY)
        self.last_signed_pdf_url: Optional[str] = None

    @property
    def base_host(self) -> str:
        if self.api_url and "www.esign.network" in self.api_url:
            return "https://www.esign.network"
        return "https://demo.esign.network"

    def get_apij_getdoc_url(self, txn: str, reference: str) -> str:
        return f"{self.base_host}/apij/getdoc/v1.0/{txn}/{reference}"

    def get_portal_url(self) -> str:
        return f"{self.base_host}/esigndoc/"

    def get_provider_name(self) -> str:
        return "Capricorn Identity Services"

    def health_check(self) -> bool:
        try:
            resp = requests.head(self.api_url, timeout=5)
            return resp.status_code in [200, 405]
        except Exception as e:
            logger.warning(f"Capricorn health check failed: {e}")
            return False

    def create_esign_request(self, document_id: str, signer_info: dict) -> dict:
        raise NotImplementedError("Use send_document_for_esign for Capricorn payload")

    def get_esign_status(self, request_id: str) -> dict:
        return {"status": "UNKNOWN", "request_id": request_id}

    def generate_unique_txn(self) -> str:
        """Generates an 8-digit unique numeric transaction ID as expected by Capricorn API."""
        return str(random.randint(10000000, 99999999))


    def convert_pdf_to_base64(self, file_path: str) -> str:
        """Reads a local PDF file and returns its Base64 encoded string without modifying the structure."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF document not found at: {file_path}")

        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        # Send the EXACT original PDF bytes. Do not rewrite with pypdf, 
        # as it crashes Capricorn's .NET parser with "Index out of bounds".
        return base64.b64encode(pdf_bytes).decode("utf-8")

    def send_document_for_esign(
        self,
        doc_title: str,
        pdf_file_path: str,
        signatory_name: str,
        signatory_mobile: Optional[str] = None,
        signatory_email: Optional[str] = None,
        callback_url: str = "",
        page_num: str = "all",
        coordinates: str = "400,20,550,90",
        sign_mode: str = "online-aadhaar-otp",
        reason: str = "Agreement sign",
        location: str = "Delhi"
    ) -> Dict[str, Any]:
        """
        Encodes the PDF to Base64 and dispatches the E-Sign request to Capricorn API.
        Returns the untouched response and extracted direct signing URLs.
        """
        pdf64_str = self.convert_pdf_to_base64(pdf_file_path)
        txn_id = self.generate_unique_txn()

        cleaned_page = str(page_num).strip().lower() if page_num else "all"
        if cleaned_page in ["all", "all pages", "allpages", "every"]:
            final_pagenum = "all"
        else:
            try:
                final_pagenum = str(int(page_num))
            except (ValueError, TypeError):
                final_pagenum = "all"

        raw_cood = str(coordinates or "").strip()
        cleaned_cood = re.sub(r'[^\d,]', '', raw_cood) if raw_cood else ""
        if cleaned_cood.count(',') == 3 and all(p.strip().isdigit() for p in cleaned_cood.split(',')):
            final_cood = cleaned_cood
        else:
            final_cood = "400,700,550,750"

        final_callback_url = (callback_url or "").strip() or "https://zoikyc.com/esign/callback"

        payload = {
            "request": {
                "auth": {
                    "token": self.token,
                    "key": self.key,
                    "command": "esign"
                },
                "parameter": {
                    "uploadpdf": {
                        "pdf64": pdf64_str,
                        "pdfurl": "",
                        "title": doc_title[:100],
                        "txn": txn_id,
                        "callbackurl": final_callback_url,
                        "signatories": {
                            "signatory": {
                                "id": "signatory1",
                                "sn": "",
                                "name": signatory_name,
                                "email": "no-reply@zoikyc.com",
                                "mail": "",
                                "mobile": "",
                                "sms": "",
                                "mode": sign_mode or "online-aadhaar-otp",
                                "ekycid": "esignnetwork",
                                "dsc": {
                                    "email": "",
                                    "serial": "",
                                    "organization": "",
                                    "orgunit": ""
                                },
                                "option": {
                                    "cood": final_cood,
                                    "pagenum": final_pagenum,
                                    "reason": reason or "Agreement sign",
                                    "location": location or "Delhi",
                                    "customtext": f"Signed by {signatory_name}",
                                    "enableltv": "",
                                    "lockpdf": "",
                                    "enablets": "",
                                    "includesubject": "",
                                    "includecn": ""
                                }
                            }
                        }
                    }
                }
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        logger.info(f"Dispatching Capricorn E-Sign request for txn={txn_id}, doc='{doc_title}'")

        try:
            resp = requests.post(self.api_url, json=payload, headers=headers, timeout=45)
            logger.info(f"Capricorn API HTTP status: {resp.status_code}")

            if resp.status_code != 200:
                logger.error(f"Capricorn API returned non-200 status {resp.status_code}: {resp.text}")
                return {
                    "success": False,
                    "error": resp.text,
                    "raw": resp.text
                }

            data = resp.json()
            response_obj = data.get("response", {})

            # Return raw error directly from Capricorn untouched
            if response_obj.get("error"):
                return {
                    "success": False,
                    "error": str(response_obj.get("error")),
                    "raw": data
                }

            # Return status_desc if status indicates failure
            status = response_obj.get("status")
            if status is not None and str(status).lower() not in ["0", "success", "ok"]:
                status_desc = response_obj.get("status_desc") or response_obj.get("error")
                if status_desc:
                    return {
                        "success": False,
                        "error": str(status_desc),
                        "raw": data
                    }

            # Extract item details
            items = response_obj.get("responsedata", {}).get("items", {}) if response_obj.get("responsedata") else {}
            item = items.get("item", {}) if isinstance(items, dict) else {}
            if isinstance(item, list) and len(item) > 0:
                item = item[0]
            elif not isinstance(item, dict):
                item = {}

            esign_url = item.get("esignurl")
            redirect_url = item.get("redirecturl")
            reference = item.get("reference")
            signed_pdf_url = item.get("signedpdfurl")
            returned_txn = item.get("txn") or txn_id

            direct_signing_url = esign_url or redirect_url

            if not direct_signing_url and not reference:
                err_msg = response_obj.get("error") or response_obj.get("status_desc") or str(data)
                return {
                    "success": False,
                    "error": str(err_msg),
                    "raw": data
                }

            return {
                "success": True,
                "txn": returned_txn,
                "reference": reference,
                "redirect_url": direct_signing_url or self.get_portal_url(),
                "esign_url": esign_url,
                "signed_pdf_url": signed_pdf_url,
                "raw": data
            }

        except requests.RequestException as e:
            logger.exception(f"Network error communicating with Capricorn API: {e}")
            return {
                "success": False,
                "error": f"Failed to connect to Capricorn E-Sign gateway: {str(e)}"
            }
        except Exception as ex:
            logger.exception(f"Unexpected error in send_document_for_esign: {ex}")
            return {
                "success": False,
                "error": f"Internal error during e-sign dispatch: {str(ex)}"
            }

    def download_signed_pdf(self, signed_pdf_url: str, target_file_path: str) -> bool:
        """
        Downloads finalized signed PDF from Capricorn URL and stores it.
        Handles direct binary stream and Base64 encoded JSON responses.
        """
        try:
            resp = requests.get(signed_pdf_url, timeout=30)
            if resp.status_code != 200:
                logger.error(f"Failed to download signed PDF: status {resp.status_code}")
                return False

            raw_bytes = getattr(resp, 'content', None)
            if not isinstance(raw_bytes, (bytes, bytearray)) and hasattr(resp, 'iter_content'):
                try:
                    raw_bytes = b''.join([c for c in resp.iter_content(chunk_size=8192) if isinstance(c, (bytes, bytearray))])
                except Exception:
                    raw_bytes = b''

            # Direct binary stream
            if isinstance(raw_bytes, (bytes, bytearray)) and raw_bytes.startswith(b'%PDF'):
                self.last_signed_pdf_url = signed_pdf_url
                os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                with open(target_file_path, "wb") as f:
                    f.write(raw_bytes)
                return True

            try:
                data = resp.json()
                resp_obj = data.get("response", {})
                resp_data = resp_obj.get("responsedata", {})
                
                viewer_url = resp_data.get("signedpdfurl") or resp_obj.get("signedpdfurl")
                if viewer_url:
                    self.last_signed_pdf_url = viewer_url

                signed_b64 = resp_data.get("signedpdf") or resp_obj.get("signedpdf")
                if signed_b64:
                    pdf_decoded = base64.b64decode(signed_b64)
                    if pdf_decoded.startswith(b'%PDF'):
                        os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                        with open(target_file_path, "wb") as f:
                            f.write(pdf_decoded)
                        return True
            except (json.JSONDecodeError, ValueError):
                pass
            return False
        except Exception as e:
            logger.exception(f"Exception downloading signed PDF: {e}")
            return False

    def get_signed_document_viewer_url(self, txn: str, reference: str) -> Optional[str]:
        """Queries Capricorn apij/getdoc to extract direct signed PDF viewer URL."""
        try:
            url = self.get_apij_getdoc_url(txn, reference)
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                resp_obj = data.get("response", {})
                resp_data = resp_obj.get("responsedata", {})
                
                viewer_url = resp_data.get("signedpdfurl") or resp_obj.get("signedpdfurl")
                if viewer_url:
                    self.last_signed_pdf_url = viewer_url
                    return viewer_url
        except Exception as e:
            logger.warning(f"Failed to fetch Capricorn signed viewer URL: {e}")
        return None
