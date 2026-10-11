import urllib.request, json

TOKEN = "8854355568:AAFfbw8Peq2YI7MJuMTyubGXKYrrpTG7kdU"

# Delete webhook
url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
req = urllib.request.Request(url, method="POST")
resp = urllib.request.urlopen(req)
print("deleteWebhook:", resp.read().decode())

# Get webhook info
url2 = f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
resp2 = urllib.request.urlopen(url2)
print("getWebhookInfo:", resp2.read().decode())
