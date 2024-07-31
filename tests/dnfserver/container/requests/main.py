import json
import requests

clientCrt = "cc.crt"
clientKey = "ck.key"
url = "https://example.com/api"
payload = { "someId": "myID" }
certServer = 'cs.crt'
headers = {'content-type': 'application/json'}
r = requests.post(url, data=json.dumps(payload), verify=certServer, 
                  headers=headers, cert=(clientCrt, clientKey))
print(r.status_code)
print(r.json())
