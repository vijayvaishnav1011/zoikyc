#!/usr/bin/env python3
"""
ZoiKYC E-Sign REST API Test Utility
Sends a test JSON payload with valid Base64 PDF to https://zoikyc.com/api/esign/<API_KEY>
"""

import sys
import json
import requests

# 1. Minimal valid 1-page PDF encoded in Base64 (RFC 2045 compliant)
SAMPLE_PDF_BASE64 = (
    "JVBERi0xLjQKMSAwIG9iajw8L1R5cGUvQ2F0YWxvZy9QYWdlcyAyIDAgUj4+ZW5kb2JqCg"
    "yIDAgb2JqPDwvVHlwZS9QYWdlcy9LaWRzWzMgMCBSXS9Db3VudCAxPj5lbmRvYmoKMyAw"
    "IG9iajw8L1R5cGUvUGFnZS9NZWRpYUJveFswIDAgNjEyIDc5Ml0vUGFyZW50IDIgMCBSL1"
    "Jlc291cmNlczw8Pj4+PmVuZG9iagp4cmVmCjAgNAowMDAwMDAwMDAwIDY1NTM1IGYgCjAw"
    "MDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1MiAwMDAwMCBuIAowMDAwMDAwMTAxIDAwMDAw"
    "IG4gCnRyYWlsZXI8PC9TaXplIDQvUm9vdCAxIDAgUj4+CnN0YXJ0eHJlZgoxNzgKJSVFT0Y="
)

# 2. Input JSON Payload
TEST_PAYLOAD = {
    "pdf_base64": SAMPLE_PDF_BASE64,
    "signatory_name": "Vijay Vaishnav",
    "signatory_mobile": "9876543210",
    "signatory_email": "vijay@zoikyc.com",
    "title": "Customer Onboarding Agreement #101",
    "page_num": "1",
    "coordinates": "200,250,400,500",
    "client_remarks": "Testing dynamic per-KYC wallet deduction"
}

def main():
    api_key = sys.argv[1] if len(sys.argv) > 1 else "zoi_live_e0db3902e4cad48886878aa236013f51"
    base_url = sys.argv[2] if len(sys.argv) > 2 else "https://zoikyc.com"
    
    endpoint = f"{base_url}/api/esign/{api_key}"
    print(f"\n🚀 Sending E-Sign test request to: {endpoint}")
    print("=" * 60)
    print("📦 Payload JSON:")
    preview = dict(TEST_PAYLOAD)
    preview["pdf_base64"] = preview["pdf_base64"][:40] + "... [TRUNCATED 424 CHARS]"
    print(json.dumps(preview, indent=2))
    print("=" * 60)

    try:
        response = requests.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json=TEST_PAYLOAD,
            timeout=30
        )
        print(f"Status Code: {response.status_code}")
        try:
            print("Response JSON:")
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print("Response Text:", response.text)
    except Exception as err:
        print(f"❌ Request failed: {err}")

if __name__ == '__main__':
    main()
