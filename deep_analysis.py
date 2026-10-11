#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

cmds = [
    # Check if DEX is valid
    'dexdump -f /tmp/test_kb.apk 2>&1 | head -30',
    # Check all native libs
    'unzip -l /tmp/test_kb.apk | grep -i "lib/"',
    # Check the wrapper DEX from TEMPL directly
    'cd /root/.sop/hathixfud-bot-kb && python3 -c "import base64; from protect_apk import TEMPL; dex = base64.b64decode(TEMPL[\"classes.dex\"][\"d\"]); print(f\"DEX size: {len(dex)}\"); print(f\"DEX magic: {dex[:8]}\")"',
    # Check for architecture-specific code in DEX
    'cd /root/.sop/hathixfud-bot-kb && python3 -c "import base64; from protect_apk import TEMPL; dex = base64.b64decode(TEMPL[\"classes.dex\"][\"d\"]); print(\"Has native methods:\", b\"System\" in dex or b\"loadLibrary\" in dex)"',
    # Verify the APK with package manager
    'pm install -t /tmp/test_kb.apk 2>&1 || true',
    # Check if the APK's classes.dex has the right class
    'dexdump /tmp/test_kb.apk 2>&1 | grep "Class descriptor" | head -20',
]

for cmd in cmds:
    print(f"\n=== {cmd[:70]}... ===")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode(errors='replace')
    err = stderr.read().decode(errors='replace')
    if out: print(out[:2000])
    if err and err != out: print("ERR:", err[:1000])

ssh.close()
