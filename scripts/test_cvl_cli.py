#!/usr/bin/env python3
"""
CVL KRA REST API Tester & Postman Payload Generator
Allows direct testing of CVL KRA GetToken and GetPanStatus APIs.
"""
import sys
import os
import json
import base64
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

def base64_url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def base64_url_decode(data: str) -> bytes:
    padded_data = data + "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(padded_data)

def cvl_encrypt(aes_key: str, data: str) -> str:
    iv = os.urandom(16)
    key = base64_url_decode(aes_key.strip())
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_data = pad(data.encode('utf-8'), AES.block_size)
    encrypted_text = cipher.encrypt(padded_data)
    return base64_url_encode(iv) + ":" + base64_url_encode(encrypted_text)

def cvl_decrypt(aes_key: str, enc_string: str) -> str:
    try:
        iv_str, cipher_str = enc_string.strip('"').split(":")
        iv = base64_url_decode(iv_str)
        cipher_bytes = base64_url_decode(cipher_str)
        key = base64_url_decode(aes_key.strip())
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_bytes = cipher.decrypt(cipher_bytes)
        return unpad(decrypted_bytes, AES.block_size).decode('utf-8')
    except Exception as e:
        return f"Decryption Error: {e}"

def test_cvl_flow(poscode, username, password, api_key, aes_key, pan="HRQPB8013L"):
    print("=" * 60)
    print(" 🚀 CVL KRA REST API Verification & Payload Generator")
    print("=" * 60)
    print(f"Target REST Endpoint : https://api.kracvl.com/int/api")
    print(f"POS Code             : {poscode}")
    print(f"Username             : {username}")
    print(f"Target PAN           : {pan}")
    print("-" * 60)

    # 1. Prepare Auth Payload
    auth_data = json.dumps({
        "username": username,
        "poscode": poscode,
        "password": password
    })
    
    try:
        encrypted_auth = cvl_encrypt(aes_key, auth_data)
    except Exception as e:
        print(f"❌ AES Encryption Failed: {e}")
        print("   Tip: Check that aes_key is a valid 24-byte Base64-URL string provided by CVL.")
        return

    print("\n📦 STEP 1: POSTMAN GetToken Details:")
    print("URL     : https://api.kracvl.com/int/api/GetToken")
    print("Method  : POST")
    print(f"Headers : Content-Type: application/json\n          api_key: {api_key}")
    print(f'Body    : "{encrypted_auth}"')

    # Send GetToken
    print("\n⏳ Sending GetToken to CVL KRA...")
    headers = {
        "Content-Type": "application/json",
        "api_key": api_key
    }
    try:
        resp = requests.post(
            "https://api.kracvl.com/int/api/GetToken",
            data=json.dumps(encrypted_auth),
            headers=headers,
            timeout=20
        )
        print(f"Status Code: {resp.status_code}")
        raw_text = resp.text.strip()
        print(f"Raw Response: {raw_text[:180]}...")

        # Decrypt response
        decrypted = cvl_decrypt(aes_key, raw_text)
        print(f"\n🔓 Decrypted Response:\n{decrypted}")

        try:
            token_json = json.loads(decrypted)
            token = token_json.get("token") or token_json.get("Token")
        except Exception:
            token = None

        if not token:
            print("\n❌ Could not extract JWT Token from CVL response.")
            return

        print(f"\n✅ JWT Token Obtained successfully!")
        print(f"Token: {token[:40]}... (len {len(token)})")

        # 2. Step 2: GetPanStatus
        pan_payload = json.dumps({
            "pan": pan,
            "poscode": poscode
        })
        enc_pan_payload = cvl_encrypt(aes_key, pan_payload)

        print("\n" + "-" * 60)
        print("📦 STEP 2: POSTMAN GetPanStatus Details:")
        print("URL     : https://api.kracvl.com/int/api/GetPanStatus")
        print("Method  : POST")
        print(f"Headers : Content-Type: application/json\n          Token: {token}\n          user-agent: CustomUsrAgnt")
        print(f'Body    : "{enc_pan_payload}"')

        print("\n⏳ Sending GetPanStatus to CVL KRA...")
        pan_headers = {
            "Content-Type": "application/json",
            "Token": token,
            "user-agent": "CustomUsrAgnt"
        }
        pan_resp = requests.post(
            "https://api.kracvl.com/int/api/GetPanStatus",
            data=json.dumps(enc_pan_payload),
            headers=pan_headers,
            timeout=20
        )
        print(f"Status Code: {pan_resp.status_code}")
        pan_raw = pan_resp.text.strip()
        print(f"Raw Response: {pan_raw[:180]}...")

        decrypted_pan = cvl_decrypt(aes_key, pan_raw)
        print(f"\n🔓 Decrypted PAN Status Response:\n{decrypted_pan}")

    except Exception as e:
        print(f"\n❌ Network or Execution Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) >= 6:
        test_cvl_flow(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6] if len(sys.argv) > 6 else "HRQPB8013L")
    else:
        print("Usage: python3 scripts/test_cvl_cli.py <poscode> <username> <password> <api_key> <aes_key> [pan]")
        print("Example: python3 scripts/test_cvl_cli.py 2500016409 user123 pass456 key_abc aes_key_xyz HRQPB8013L")
