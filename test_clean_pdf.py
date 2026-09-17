import requests, json, base64, random
from reportlab.pdfgen import canvas
import io

# 1. Generate a perfectly clean, flat PDF
buf = io.BytesIO()
c = canvas.Canvas(buf)
c.drawString(100, 750, 'ZoiKYC Test Agreement')
c.save()

# 2. Encode to Base64
pdf_bytes = buf.getvalue()
pdf64_str = base64.b64encode(pdf_bytes).decode("utf-8")

# 3. Create payload with EMPTY pdfurl, relying ONLY on pdf64
payload = {
    "request": {
        "auth": {
            "token": "1D70678680F404BF92E4618FDF5D39A518D9F192",
            "key": "hLIc0TqVMt6aH4asHxpqlwloVZfL7raq8X8NSWu2OVCo$$$$$$shodIaK5g==",
            "command": "esign"
        },
        "parameter": {
            "uploadpdf": {
                "pdf64": pdf64_str,
                "pdfurl": "",
                "title": "Clean Test Doc",
                "txn": str(random.randint(10000000, 99999999)),
                "callbackurl": "http://example.com/cb",
                "signatories": {
                    "signatory": {
                        "id": "signatory1",
                        "sn": "",
                        "name": "Pankaj",
                        "email": "no-reply@zoikyc.com",
                        "mail": "",
                        "mobile": "",
                        "sms": "",
                        "mode": "online-aadhaar-otp",
                        "ekycid": "esignnetwork",
                        "dsc": {
                            "email": "",
                            "serial": "",
                            "organization": "",
                            "orgunit": ""
                        },
                        "option": {
                            "cood": "400,700,550,750",
                            "pagenum": "all",
                            "reason": "Agreement",
                            "location": "Delhi",
                            "customtext": "Signed",
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

print("Sending a brand new clean PDF via pdf64...")
r = requests.post("https://www.esign.network/op/api/v1.0/postjson", json=payload, headers={"Content-Type":"application/json"})
print(json.dumps(r.json(), indent=2))
