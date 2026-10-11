#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# Build with KB bot
print("=== Building with KB bot (fixed) ===")
stdin, stdout, stderr = ssh.exec_command(
    'cd /root/.sop/hathixfud-bot-kb && python3 protect_apk.py --apk /tmp/test_input.apk -o /tmp/test_fixed.apk 2>&1',
    timeout=120)
print(stdout.read().decode())
print(stderr.read().decode())

# Verify signing
print("=== Signing verification ===")
stdin, stdout, stderr = ssh.exec_command('apksigner verify --verbose /tmp/test_fixed.apk 2>&1')
print(stdout.read().decode())
print(stderr.read().decode())

# Check aapt
print("=== AAPT dump ===")
stdin, stdout, stderr = ssh.exec_command('aapt dump badging /tmp/test_fixed.apk 2>&1 | head -10')
print(stdout.read().decode())

# Check zipalign
print("=== Zipalign check ===")
stdin, stdout, stderr = ssh.exec_command('zipalign -c -v 4 /tmp/test_fixed.apk 2>&1 | tail -3')
print(stdout.read().decode())

# Compare with original APK structure
print("=== Full manifest tree ===")
stdin, stdout, stderr = ssh.exec_command('aapt dump xmltree /tmp/test_fixed.apk AndroidManifest.xml 2>&1')
print(stdout.read().decode())

ssh.close()
