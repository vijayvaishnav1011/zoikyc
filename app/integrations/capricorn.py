import os
import base64
import json
import logging
import random
import requests
from datetime import datetime
from typing import Dict, Any, Optional
from flask import current_app
from app.integrations.base import BaseESignProvider

logger = logging.getLogger(__name__)

class CapricornESignProvider(BaseESignProvider):
    """
    Integration provider for Capricorn Identity Services E-Sign API (demo.esign.network).
    Supports Base64 PDF transmission, online-aadhaar-otp signing, and signed document retrieval.
    """

    POST_JSON_URL = "https://demo.esign.network/op/api/v1.0/postjson"
    POST_XML_URL = "https://demo.esign.network/op/api/v1.0/postxml"
    DEFAULT_API_URL = POST_JSON_URL
    DEFAULT_TOKEN = "4352F73EEDAB18ADEAF33FDA7C35BC9013E5E704"
    DEFAULT_KEY = "QkXVeIcZZtdNvPnotGoXqG4hO9Os0@@@@@@sfp4bigUC4pgZTgUrKS4Tkew=="

    def __init__(self, api_url: Optional[str] = None, token: Optional[str] = None, key: Optional[str] = None):
        self.api_url = api_url or os.environ.get('CAPRICORN_API_URL', self.DEFAULT_API_URL)
        self.token = token or os.environ.get('CAPRICORN_API_TOKEN', self.DEFAULT_TOKEN)
        self.key = key or os.environ.get('CAPRICORN_API_KEY', self.DEFAULT_KEY)

    def get_provider_name(self) -> str:
        return "Capricorn Identity Services"

    def health_check(self) -> bool:
        try:
            # Capricorn doesn't have an explicit ping endpoint, check if URL is reachable
            resp = requests.head(self.api_url, timeout=5)
            return resp.status_code in [200, 405]
        except Exception as e:
            logger.warning(f"Capricorn health check failed: {e}")
            return False

    def create_esign_request(self, document_id: str, signer_info: dict) -> dict:
        """Required by BaseESignProvider interface."""
        raise NotImplementedError("Use send_document_for_esign for full Capricorn payload")

    def get_esign_status(self, request_id: str) -> dict:
        """Fetches status of an e-sign request if provider supports polling."""
        return {"status": "UNKNOWN", "request_id": request_id}

    def generate_unique_txn(self) -> str:
        """Generates an 8-digit unique numeric transaction ID as expected by Capricorn API."""
        return str(random.randint(10000000, 99999999))

    def convert_pdf_to_base64(self, file_path: str) -> str:
        """Reads a local PDF file and returns its Base64 encoded string."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF document not found at: {file_path}")
        
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
        return base64.b64encode(pdf_bytes).decode("utf-8")

    def send_document_for_esign(
        self,
        doc_title: str,
        pdf_file_path: str,
        signatory_name: str,
        signatory_mobile: str,
        signatory_email: Optional[str],
        callback_url: str,
        page_num: str = "1",
        coordinates: str = "200,250,400,500",
        sign_mode: str = "online-aadhaar-otp"
    ) -> Dict[str, Any]:
        """
        Encodes the PDF to Base64 (pdf64) and dispatches the E-Sign request to Capricorn API.
        Returns parsed dictionary containing redirecturl, reference, signedpdfurl, and txn.
        """
        pdf64_str = self.convert_pdf_to_base64(pdf_file_path)
        txn_id = self.generate_unique_txn()

        # Handle page_num formatting: if integer-like convert to int
        try:
            parsed_pagenum = int(page_num)
        except (ValueError, TypeError):
            parsed_pagenum = page_num if page_num in ['all', 'custom'] else 1

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
                        "callbackurl": callback_url,
                        "signatories": {
                            "signatory": [
                                {
                                    "id": "signatory1",
                                    "sn": "1",
                                    "name": signatory_name,
                                    # Privacy Protection: Do not send client's real email/phone to Capricorn
                                    "email": "na@zoikyc.com",
                                    "mail": "n",
                                    "mobile": "9999999999",
                                    "sms": "n",
                                    "mode": sign_mode or "online-aadhaar-otp",
                                    "ekycid": "esignnetwork",
                                    "dsc": {
                                        "email": "",
                                        "serial": "",
                                        "organization": "",
                                        "orgunit": ""
                                    },
                                    "option": {
                                        "cood": coordinates,
                                        "pagenum": parsed_pagenum,
                                        "reason": "Agreement Execution & Verification",
                                        "location": "India",
                                        "customtext": f"Digitally Signed by {signatory_name}",
                                        "enableltv": "no",
                                        "disablegreentick": "no",
                                        "lockpdf": "no",
                                        "enablets": "no",
                                        "includesubject": "no",
                                        "includecn": "no"
                                    }
                                }
                            ]
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
                    "error": f"Capricorn API error (HTTP {resp.status_code}): {resp.text[:200]}"
                }

            data = resp.json()
            response_obj = data.get("response", {})

            # Check if there is an explicit error
            if response_obj.get("error"):
                return {
                    "success": False,
                    "error": str(response_obj.get("error"))
                }

            # Extract item details
            items = response_obj.get("responsedata", {}).get("items", {})
            item = items.get("item", {})

            redirect_url = item.get("redirecturl")
            reference = item.get("reference")
            signed_pdf_url = item.get("signedpdfurl")
            returned_txn = item.get("txn") or txn_id

            if not redirect_url and not reference:
                return {
                    "success": False,
                    "error": f"Capricorn did not return redirect URL. Raw response: {data}"
                }

            # Resolve to direct live demo.esign.digital portal URL
            direct_signing_url = redirect_url
            if redirect_url:
                try:
                    head_resp = requests.get(redirect_url, allow_redirects=False, timeout=10)
                    loc = head_resp.headers.get("Location") or head_resp.headers.get("location")
                    if loc and "?param=" in loc:
                        param = loc.split("?param=")[-1]
                        direct_signing_url = f"https://demo.esign.digital/esign/2.1/signdockyc/?param={param}"
                    elif "demo.esign.network" in redirect_url:
                        direct_signing_url = redirect_url.replace("demo.esign.network", "demo.esign.digital")
                except Exception as e:
                    logger.warning(f"Failed resolving direct demo.esign.digital signdockyc URL: {e}")
                    if "demo.esign.network" in redirect_url:
                        direct_signing_url = redirect_url.replace("demo.esign.network", "demo.esign.digital")

            return {
                "success": True,
                "txn": returned_txn,
                "reference": reference,
                "redirect_url": direct_signing_url or "https://demo.esign.digital/esign/2.1/signdockyc/",
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
        """Downloads the finalized digitally signed PDF from Capricorn URL and stores it."""
        try:
            resp = requests.get(signed_pdf_url, timeout=30, stream=True)
            if resp.status_code == 200:
                os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                with open(target_file_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            logger.error(f"Failed to download signed PDF from {signed_pdf_url}, status code: {resp.status_code}")
            return False
        except Exception as e:
            logger.exception(f"Exception downloading signed PDF from {signed_pdf_url}: {e}")
            return False
