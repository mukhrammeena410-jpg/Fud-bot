#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

sftp = ssh.open_sftp()
sftp.put(r'C:\Users\Lucky\OneDrive\Desktop\Advance Fud bot\hathixfud\protect_apk.py',
         '/root/.sop/hathixfud-bot-kb/protect_apk.py')
sftp.close()
print("Uploaded protect_apk.py")

ssh.exec_command('systemctl restart hathixfud-bot-kb')

import time
time.sleep(5)
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hathixfud-bot-kb')
print("Status:", stdout.read().decode().strip())

# Test build
print("\n=== Test build ===")
stdin, stdout, stderr = ssh.exec_command(
    'cd /root/.sop/hathixfud-bot-kb && python3 protect_apk.py --apk /tmp/test_input.apk -o /tmp/test_deployed.apk 2>&1',
    timeout=120)
print(stdout.read().decode())
print(stderr.read().decode())

# Verify
print("\n=== Verify ===")
stdin, stdout, stderr = ssh.exec_command('aapt dump badging /tmp/test_deployed.apk 2>&1 | head -5')
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command('aapt dump xmltree /tmp/test_deployed.apk AndroidManifest.xml 2>&1 | head -10')
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command('apksigner verify --verbose /tmp/test_deployed.apk 2>&1')
print(stdout.read().decode())

ssh.close()
