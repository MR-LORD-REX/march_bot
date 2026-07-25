
import requests 

url="https://ilcapitano01-gi-card-api.hf.space/getcals"
data={
    "uid":"800556377",
    "slot":1,
    "benchmark":True
}
response=requests.post(url,json=data)
with open("response.json","w") as f:
    import json
    json.dump(response.json(),f)