#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# Test: compare original bot output vs KB bot output
cmds = [
    # Check if original bot exists and has APKs
    'ls -la /root/.sop/hathixfud-bot/ 2>&1 | head -10',
    # Check the wrapper template
    'cd /root/.sop/hathixfud-bot-kb && python3 -c "from protect_apk import TEMPL, ORDER; import base64; dex = base64.b64decode(TEMPL[\"classes.dex\"][\"d\"]); print(f\"classes.dex size: {len(dex)} bytes, header: {dex[:4].hex()}\"); manifest = base64.b64decode(TEMPL[\"AndroidManifest.xml\"][\"d\"]); print(f\"AndroidManifest.xml size: {len(manifest)} bytes\")"',
    # Check the pack/unpack round-trip with manifest
    'cd /root/.sop/hathixfud-bot-kb && python3 -c "from protect_apk import pack, unpack, TEMPL, PAYLOAD_NAME; import base64; payload = b\"TEST_PAYLOAD_DATA_12345\"; z = pack(payload, {}, [], None); u = unpack(z); print(f\"round-trip match: {u == payload}\"); print(f\"entries: {list(z.infolist().__iter__().__next__().filename for _ in range(3))}\")"',
]

for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(f"CMD: {cmd[:80]}...")
    if out: print(out)
    if err: print("STDERR:", err)

ssh.close()
