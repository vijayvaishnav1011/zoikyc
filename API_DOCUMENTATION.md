# ZoiKYC API Documentation

Welcome to the **ZoiKYC Developer API Documentation**. This guide provides complete details, request payloads, response structures, signing workflows, and error handling for:
1. **PAN Verification API** (powered by CVL KRA GetPANStatus)
2. **Aadhaar E-Sign API** (powered by Capricorn Identity Services)

---

## 1. Authentication & Base URLs

All API calls are authenticated using your unique organisation **API Key** (format: `zoi_live_...` or your Client ID).

### Production Base URL
```
https://zoikyc.com
```

### Supported Authentication Methods
You can pass your API key via any of the following 3 ways:

| Method | Example |
| :--- | :--- |
| **URL Path (Recommended)** | `https://zoikyc.com/api/pan/<YOUR_API_KEY>` |
| **HTTP Header (`X-API-Key`)** | `X-API-Key: <YOUR_API_KEY>` |
| **Bearer Token Header** | `Authorization: Bearer <YOUR_API_KEY>` |

---

## 2. PAN Verification API

The PAN Verification service validates 10-character Indian Permanent Account Numbers against the official **CVL KRA** registry with date of birth (DOB) matching and Aadhaar seeding status check.

### 2.1 Service Health / Info Check
Check if the PAN Verification service is online.

- **Method**: `GET`
- **URL**: `https://zoikyc.com/api/pan/<YOUR_API_KEY>`

#### Response (`200 OK`):
```json
{
  "service": "ZoiKYC PAN Verification API",
  "status": "online",
  "method": "POST",
  "message": "Send a POST request with 'pan' and 'dob' in JSON body to verify."
}
```

---

### 2.2 Verify PAN with Date of Birth
Validates a PAN and verifies whether the provided Date of Birth matches government records.

- **Method**: `POST`
- **URL**: `https://zoikyc.com/api/pan/<YOUR_API_KEY>`
- **Content-Type**: `application/json`

#### Request Headers:
```http
Content-Type: application/json
```

#### Request Payload:
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `pan` | `string` | **Yes** | 10-character PAN number (e.g. `ABCDE1234F`). Case-insensitive. |
| `dob` | `string` | **Yes** | Date of Birth in `DD/MM/YYYY` format (e.g. `15/08/1990`). |

*(Alternative: You can pass `dob_day`, `dob_month`, and `dob_year` individually).*

#### Example Request Body:
```json
{
  "pan": "ABCDE1234F",
  "dob": "15/08/1990"
}
```

#### Example cURL Command:
```bash
curl -X POST "https://zoikyc.com/api/pan/zoi_live_YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "pan": "ABCDE1234F",
    "dob": "15/08/1990"
  }'
```

---

#### Success Response (`200 OK` - Verified Record):
```json
{
  "success": true,
  "status": "verified",
  "pan": "ABCDE1234F",
  "full_name": "PANKAJ VAISHNAV",
  "first_name": "PANKAJ",
  "middle_name": "",
  "last_name": "VAISHNAV",
  "category": "Individual",
  "pan_status": "Existing and Valid",
  "dob_match": true,
  "aadhaar_seeding": "OPERATIVE / SEEDED",
  "status_message": "PAN verified successfully with CVL KRA.",
  "reference_id": "PAN_1726041234",
  "record_id": 142,
  "method": "GetPANStatus",
  "organisation": "Alpha Corp",
  "client_id": "CLI-ALPHA-01",
  "duration_ms": 320
}
```

#### Field Descriptions:
- `success` (`boolean`): `true` if CVL KRA returned an existing valid PAN record.
- `status` (`string`): `"verified"` (found & matched), or `"failed"`.
- `full_name` (`string`): Full legal name registered with the Income Tax Department.
- `category` (`string`): `"Individual"`, `"Company"`, `"HUF"`, etc.
- `pan_status` (`string`): Official ITD status (e.g. `"Existing and Valid"`).
- `dob_match` (`boolean`): `true` if DOB matches CVL record, `false` otherwise.
- `aadhaar_seeding` (`string`): Aadhaar link status (`"OPERATIVE / SEEDED"`, `"INOPERATIVE"`, or `"NOT APPLICABLE"`).
- `duration_ms` (`integer`): Time taken by CVL KRA gateway in milliseconds.

---

#### Error & Failure Responses:

##### 1. Invalid PAN Format (`400 Bad Request`)
```json
{
  "success": false,
  "status": "invalid",
  "error": "Invalid PAN format: 'ABC12'. PAN must be 10 characters (5 letters, 4 digits, 1 letter)."
}
```

##### 2. Missing Required Fields (`400 Bad Request`)
```json
{
  "success": false,
  "status": "invalid",
  "error": "Missing required field: 'dob'. Date of Birth is required (format DD/MM/YYYY)."
}
```

##### 3. Authentication Failed (`401 Unauthorized`)
```json
{
  "success": false,
  "status": "unauthorized",
  "error": "Authentication Key required. Pass your API key in URL path: /api/pan/<api_key> or header X-API-Key."
}
```

##### 4. Invalid API Key (`404 Not Found`)
```json
{
  "success": false,
  "status": "not_found",
  "error": "Invalid API Key: 'invalid_key'. No active organisation found with this key."
}
```

##### 5. CVL KRA Gateway Not Configured (`400 Bad Request`)
```json
{
  "success": false,
  "status": "gateway_not_configured",
  "error": "CVL KRA credentials are not configured for organisation 'Alpha Corp'. The administrator must set up the POS Code, Username, Password, and AES key for this organisation in the Admin Portal."
}
```

##### 6. PAN Not Found in Government Database (`200 OK` with failed status)
```json
{
  "success": false,
  "status": "failed",
  "pan": "ABCDE1234F",
  "status_message": "PAN not found in CVL KRA database or DOB mismatch.",
  "full_name": null,
  "pan_status": "Invalid / Not Found",
  "dob_match": false,
  "aadhaar_seeding": null,
  "duration_ms": 280
}
```

---

## 3. Aadhaar E-Sign API

ZoiKYC provides legally binding digital signature execution under the Indian IT Act 2000 through **Capricorn Identity Services**.

### Workflow Overview:
1. **Dispatch**: Your system calls `POST /api/esign/<API_KEY>` with the PDF and signatory details.
2. **Sign URL Delivered**: ZoiKYC prepares the document and returns a live `sign_url` and a `download_url`.
3. **Signatory OTP Signing**: The customer opens `sign_url` in any web or mobile browser, enters their 12-digit Aadhaar / VID number, and receives an OTP on their Aadhaar-registered mobile number.
4. **Instant Viewer Redirect**: Once the signatory enters the OTP, the browser **automatically redirects directly to the Capricorn signed PDF viewer URL** (`signedpdfurl`).
5. **Wallet Debiting**: Your wallet is charged **only when the document is successfully signed** (`charges_on_completion`).
6. **Fetch / Download**: Retrieve signed status via `GET /api/esign/<API_KEY>/<doc_id>` or download binary PDF via `GET /api/esign/<API_KEY>/<doc_id>/download`.

---

### 3.1 Dispatch Document for E-Sign
Dispatches a PDF document for Aadhaar OTP e-signature.

- **Method**: `POST`
- **URL**: `https://zoikyc.com/api/esign/<YOUR_API_KEY>`
- **Content-Type**: `application/json` (with Base64 PDF) OR `multipart/form-data` (with file upload)

#### Request Parameters:

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `title` | `string` | **Yes** | — | Document title (e.g., `"Vendor Agreement"`). |
| `signatory_name` | `string` | **Yes** | — | Signatory name (must match name on Aadhaar). |
| `signatory_mobile`| `string` | **Yes** | — | 10-digit mobile number of the signatory. |
| `signatory_email` | `string` | No | `""` | Email of the signatory. |
| `file_base64` | `string` | **Yes\*** | — | Base64-encoded PDF string (used with JSON body). |
| `file` | `file` | **Yes\*** | — | Binary PDF file (used with `multipart/form-data`). |
| `page_num` | `string` | No | `"all"` | `"all"` to sign every page, or page number (`"1"`, `"2"`). |
| `cood` / `coordinates` | `string` | No | `"400,20,550,90"` | Signature box coordinates `x1,y1,x2,y2` on page. |
| `sign_mode` | `string` | No | `"online-aadhaar-otp"` | Signature mode. |
| `reason` | `string` | No | `"Aadhaar E-Sign Verification"` | Signing reason. |
| `location` | `string` | No | `"India"` | Signing location. |

*\* Note: Supply either `file_base64` (JSON) or `file` (multipart).*

#### Example A: JSON with Base64 PDF
```json
{
  "title": "Employment Agreement",
  "signatory_name": "Pankaj Vaishnav",
  "signatory_mobile": "9876543210",
  "signatory_email": "pankaj@example.com",
  "page_num": "all",
  "cood": "400,20,550,90",
  "file_base64": "JVBERi0xLjQKJcTl8uXrp/ogMQowIG9ia..."
}
```

#### Example B: cURL with Multipart File Upload
```bash
curl -X POST "https://zoikyc.com/api/esign/zoi_live_YOUR_API_KEY" \
  -F "title=Employment Agreement" \
  -F "signatory_name=Pankaj Vaishnav" \
  -F "signatory_mobile=9876543210" \
  -F "page_num=all" \
  -F "file=@/path/to/contract.pdf;type=application/pdf"
```

---

#### Success Response (`200 OK` - Document Ready for Signing):
```json
{
  "success": true,
  "status": "ready_for_signing",
  "message": "Document successfully created and dispatched for Aadhaar E-Sign. Wallet will be charged once signing is completed.",
  "document_id": 9,
  "reference_id": "OHIUIR9J7MVTAV0",
  "txn_id": "84933947",
  "sign_url": "https://demo.esign.network/api/esign/v1.0/84933947/OHIUIR9J7MVTAV0/signatory1/continue",
  "download_url": "https://zoikyc.com/api/esign/zoi_live_YOUR_API_KEY/9/download",
  "signatory_name": "Pankaj Vaishnav",
  "signatory_mobile": "9876543210",
  "title": "Employment Agreement",
  "billing_status": "charges_on_completion",
  "per_sign_fee": 35.0,
  "cost_charged": 0.0,
  "wallet_balance": 4895.0,
  "created_at": "2026-09-10T16:34:05.000361"
}
```

#### Key Fields:
- `sign_url`: **Share this URL with the signatory**. Opening this URL presents the Aadhaar OTP signing interface.
- `download_url`: Permanent endpoint to download the document or finalized signed PDF.
- `billing_status`: Set to `"charges_on_completion"`. Initial dispatch fee is `0.0`. Wallet will only be charged when the signature is finalized.

---

### 3.2 Check E-Sign Document Status
Returns current status, audit trail timestamps, and if signed, the direct Capricorn viewer link (`signedpdfurl`).

- **Method**: `GET`
- **URL**: `https://zoikyc.com/api/esign/<YOUR_API_KEY>/<DOCUMENT_ID>`

#### Response: While Awaiting Signature (`status: "sent_to_capricorn"`)
```json
{
  "success": true,
  "document": {
    "id": 9,
    "title": "Employment Agreement",
    "status": "sent_to_capricorn",
    "status_label": "Awaiting Aadhaar OTP",
    "signatory_name": "Pankaj Vaishnav",
    "signatory_mobile": "9876543210",
    "signatory_email": "pankaj@example.com",
    "capricorn_txn": "84933947",
    "capricorn_reference": "OHIUIR9J7MVTAV0",
    "sign_url": "https://demo.esign.network/api/esign/v1.0/84933947/OHIUIR9J7MVTAV0/signatory1/continue",
    "download_url": "https://zoikyc.com/api/esign/zoi_live_YOUR_API_KEY/9/download",
    "cost_charged": 0.0,
    "created_at": "2026-09-10T16:34:05.000361",
    "dispatched_at": "2026-09-10T16:34:06.120400",
    "signed_at": null,
    "company": {
      "id": 2,
      "name": "Alpha Corp",
      "client_id": "CLI-ALPHA-01"
    }
  }
}
```

#### Response: Once Signatory Completes Aadhaar OTP (`status: "signed"`)
```json
{
  "success": true,
  "document": {
    "id": 9,
    "title": "Employment Agreement",
    "status": "signed",
    "status_label": "Signed & Verified",
    "signatory_name": "Pankaj Vaishnav",
    "signatory_mobile": "9876543210",
    "signatory_email": "pankaj@example.com",
    "capricorn_txn": "84933947",
    "capricorn_reference": "OHIUIR9J7MVTAV0",
    "sign_url": "https://demo.esign.network/api/esign/v1.0/84933947/OHIUIR9J7MVTAV0/signatory1/continue",
    "signedpdfurl": "https://demo.esign.network/docs/signed/?p=JLjvcsMZBeE@@@@@@LctB0kTB0DgeuMuhxRmoowy2iddoVbZ7TcShtXuHBA==",
    "download_url": "https://zoikyc.com/api/esign/zoi_live_YOUR_API_KEY/9/download",
    "cost_charged": 35.0,
    "created_at": "2026-09-10T16:34:05.000361",
    "dispatched_at": "2026-09-10T16:34:06.120400",
    "signed_at": "2026-09-10T16:36:12.894310",
    "company": {
      "id": 2,
      "name": "Alpha Corp",
      "client_id": "CLI-ALPHA-01"
    }
  }
}
```

> [!NOTE]
> `signedpdfurl` is only included in the response once OTP signing is successfully completed.

---

### 3.3 Download Signed PDF
Directly streams or downloads the finalized digitally signed PDF file from ZoiKYC secure local storage.

- **Method**: `GET`
- **URL**: `https://zoikyc.com/api/esign/<YOUR_API_KEY>/<DOCUMENT_ID>/download`

#### Response When Signed:
- **HTTP Status**: `200 OK`
- **Content-Type**: `application/pdf`
- **Content-Disposition**: `attachment; filename="Signed_Employment_Agreement.pdf"`
- **Body**: Binary `%PDF` stream with DSC certificates and Aadhaar e-Sign mark embedded on every page.

#### Response When Not Yet Signed:
- **HTTP Status**: `404 Not Found`
```json
{
  "success": false,
  "status": "pending_or_not_found",
  "error": "Signed PDF is not available yet. Signatory may not have completed Aadhaar OTP."
}
```

---

### 3.4 Capricorn Callback & Browser Redirect
When the signatory enters the OTP and Capricorn verifies the Aadhaar signature:
1. Capricorn redirects the user's browser to the callback URL: `https://zoikyc.com/esign/callback?txn=...&reference=...`.
2. ZoiKYC marks the document as `signed`, records the signed PDF, and debits your wallet.
3. The server immediately returns an **HTTP 302 redirect directly to Capricorn's official viewer URL**:
   ```
   https://demo.esign.network/docs/signed/?p=...
   ```
   The customer views their signed copy in the browser.

#### If invoked as a Webhook (POST JSON):
```json
{
  "status": "success",
  "doc_id": 9,
  "signedpdfurl": "https://demo.esign.network/docs/signed/?p=JLjvcsMZBeE@@@@@@LctB0kTB0DgeuMuhxRmoowy2iddoVbZ7TcShtXuHBA==",
  "download_url": "https://zoikyc.com/api/esign/zoi_live_YOUR_API_KEY/9/download",
  "cost_charged": 35.0
}
```

---

### 3.5 E-Sign Errors & Edge Cases:

##### 1. Insufficient Wallet Balance (`402 Payment Required`)
```json
{
  "success": false,
  "status": "insufficient_balance",
  "error": "Insufficient wallet balance. Current: ₹15.00, Required: ₹35.00. Please recharge your wallet."
}
```

##### 2. Missing PDF Content (`400 Bad Request`)
```json
{
  "success": false,
  "status": "invalid_payload",
  "error": "Missing PDF document. Upload a 'file' parameter (multipart/form-data) or supply 'file_base64' in JSON body."
}
```

##### 3. Missing Signatory Details (`400 Bad Request`)
```json
{
  "success": false,
  "status": "invalid_payload",
  "error": "Missing required fields: 'signatory_name' and 'signatory_mobile' are mandatory."
}
```

##### 4. Invalid API Key (`401 Unauthorized`)
```json
{
  "success": false,
  "status": "unauthorized",
  "error": "Authentication Key required. Pass your API key in URL path: /api/esign/<api_key> or header X-API-Key."
}
```

##### 5. Suspended Account (`403 Forbidden`)
```json
{
  "success": false,
  "status": "forbidden",
  "error": "Organisation 'Alpha Corp' is currently suspended. Please contact support."
}
```

---

## 4. Code Integration Examples

### Python (using `requests`)

```python
import requests
import base64

API_KEY = "zoi_live_YOUR_API_KEY"

# 1. Verify PAN
def verify_pan(pan, dob):
    url = f"https://zoikyc.com/api/pan/{API_KEY}"
    payload = {"pan": pan, "dob": dob}
    res = requests.post(url, json=payload)
    return res.json()

# 2. Dispatch Document for E-Sign
def dispatch_esign(pdf_path, title, signer_name, signer_mobile):
    url = f"https://zoikyc.com/api/esign/{API_KEY}"
    with open(pdf_path, "rb") as f:
        pdf_b64 = base64.b64encode(f.read()).decode("utf-8")
    
    payload = {
        "title": title,
        "signatory_name": signer_name,
        "signatory_mobile": signer_mobile,
        "page_num": "all",
        "coordinates": "400,700,550,750",
        "file_base64": pdf_b64
    }
    res = requests.post(url, json=payload)
    return res.json()

# 3. Check Document Status
def check_esign_status(doc_id):
    url = f"https://zoikyc.com/api/esign/{API_KEY}/{doc_id}"
    res = requests.get(url)
    return res.json()

# 4. Download Signed PDF
def download_signed_pdf(doc_id, output_path):
    url = f"https://zoikyc.com/api/esign/{API_KEY}/{doc_id}/download"
    res = requests.get(url, stream=True)
    if res.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Downloaded signed PDF to {output_path}")
    else:
        print(f"Failed to download: {res.json()}")
```

### Node.js (using `axios`)

```javascript
const axios = require('axios');
const fs = require('fs');

const API_KEY = 'zoi_live_YOUR_API_KEY';

// 1. Verify PAN
async function verifyPan(pan, dob) {
  const res = await axios.post(`https://zoikyc.com/api/pan/${API_KEY}`, {
    pan,
    dob
  });
  return res.data;
}

// 2. Dispatch E-Sign
async function dispatchEsign(pdfPath, title, signerName, signerMobile) {
  const pdfBuffer = fs.readFileSync(pdfPath);
  const pdfBase64 = pdfBuffer.toString('base64');

  const res = await axios.post(`https://zoikyc.com/api/esign/${API_KEY}`, {
    title,
    signatory_name: signerName,
    signatory_mobile: signerMobile,
    page_num: 'all',
    coordinates: '400,700,550,750',
    file_base64: pdfBase64
  });
  return res.data;
}

// 3. Check E-Sign Status
async function checkEsignStatus(docId) {
  const res = await axios.get(`https://zoikyc.com/api/esign/${API_KEY}/${docId}`);
  return res.data;
}
```

---

## 5. Support & Troubleshooting

If you encounter unexpected errors or have questions regarding gateway setups:
- **Admin Portal**: Manage your CVL KRA credentials, wallet balance, and API keys at [https://zoikyc.com/admin/](https://zoikyc.com/admin/)
- **Support Email**: [info@zoikyc.com](mailto:info@zoikyc.com)
- **Live Capricorn Gateway**: [https://demo.esign.network/esigndoc/](https://demo.esign.network/esigndoc/)
