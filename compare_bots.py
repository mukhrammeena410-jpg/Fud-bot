#!/usr/bin/env python3
import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

cmds = [
    # Check original bot's protect_apk.py for comparison
    "diff /root/.sop/hathixfud-bot/protect_apk.py /root/.sop/hathixfud-bot-kb/protect_apk.py | head -200",
]

for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(f"=== {cmd[:60]} ===")
    print(out[:3000])
    if err:
        print("STDERR:", err[:500])

ssh.close()
