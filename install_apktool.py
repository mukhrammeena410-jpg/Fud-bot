#!/usr/bin/env python3
"""Install apktool and rebuild the wrapper manifest with versionCode."""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# Step 1: Install apktool
print("=== Installing apktool ===")
cmds = [
    'apt-get update -qq && apt-get install -y -qq apktool 2>&1 | tail -5',
    'which apktool 2>&1 || (wget -q https://raw.githubusercontent.com/iBotPeaches/Apktool/master/scripts/linux/apktool -O /usr/local/bin/apktool && wget -q https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.9.3.jar -O /usr/local/bin/apktool.jar && chmod +x /usr/local/bin/apktool && echo "apktool installed manually")',
]

for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out: print(out[-500:])
    if err: print("ERR:", err[-500:])

# Step 2: Check if apktool is available
stdin, stdout, stderr = ssh.exec_command('apktool --version 2>&1')
print("apktool version:", stdout.read().decode().strip())

ssh.close()
