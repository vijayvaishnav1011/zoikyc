import requests
import json
import ssl

def test_capricorn():
    url = "https://www.esign.network/op/api/v1.0/postjson"
    
    payload = {
        "request": {
            "auth": {
                "token": "1D70678680F404BF92E4618FDF5D39A518D9F192",
                "key": "hLIc0TqVMt6aH4asHxpqlwloVZfL7raq8X8NSWu2OVCo$$$$$$shodIaK5g==",
                "command": "esign"
            },
            "parameter": {
                "uploadpdf": {
                    "pdf64": "",
                    "pdfurl": "https://www.managexindia.com/esign.pdf",
                    "title": "For pdf sign",
                    "txn": "04629565",
                    "callbackurl": "http://94.136.189.142/getpdf",
                    "signatories": {
                        "signatory": {
                            "id": "signatory1",
                            "sn": "",
                            "name": "Aniket",
                            "email": "aniket@ideasand.com",
                            "mail": "y",
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
                            "option":{
                                "cood":"100,250,200,500",
                                "pagenum":"all",
                                "reason":"Aggreement sign",
                                "location":"Delhi",
                                "customtext":"Signed by Aniket",
                                "enableltv":"",
                                "lockpdf":"",
                                "enablets":"",
                                "includesubject":"",
                                "includecn":""
                            }
                        }
                    }
                }
            }
        }
    }

    headers = {
        'Content-Type': 'application/json'
    }

    print(f"Sending direct test request to: {url}")
    print("Using pdfurl: https://www.managexindia.com/esign.pdf")
    
    try:
        response = requests.post(
            url, 
            json=payload, 
            headers=headers, 
            timeout=60,
            verify=False # Bypass SSL verification for testing just in case
        )
        
        print("\n--- RESPONSE FROM CAPRICORN ---")
        print(f"HTTP Status: {response.status_code}")
        
        try:
            json_response = response.json()
            print("\nResponse JSON:")
            print(json.dumps(json_response, indent=2))
        except:
            print("\nRaw Response Text:")
            print(response.text)
            
    except Exception as e:
        print(f"\nRequest failed: {str(e)}")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    test_capricorn()
