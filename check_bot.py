import urllib.request

TOKEN = "8854355568:AAFfbw8Peq2YI7MJuMTyubGXKYrrpTG7kdU"
url = f"https://api.telegram.org/bot{TOKEN}/getMe"
resp = urllib.request.urlopen(url)
print(resp.read().decode())
