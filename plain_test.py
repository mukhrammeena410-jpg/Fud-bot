#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# Build plain APK
print("=== Building plain APK ===")
stdin, stdout, stderr = ssh.exec_command(
    'cd /root/.sop/hathixfud-bot-kb && python3 protect_apk.py '
    '--apk /tmp/test_input.apk -o /tmp/test_plain.apk 2>&1',
    timeout=120)
print(stdout.read().decode())
print(stderr.read().decode())

# Now install it via adb if possible
print("=== Trying adb install ===")
stdin, stdout, stderr = ssh.exec_command(
    'which adb 2>&1; adb devices 2>&1; adb install /tmp/test_plain.apk 2>&1',
    timeout=30)
print(stdout.read().decode())
print(stderr.read().decode())

# Check the full manifest tree of the plain APK
print("=== Full aapt dump ===")
stdin, stdout, stderr = ssh.exec_command(
    'aapt dump xmltree /tmp/test_plain.apk AndroidManifest.xml 2>&1')
print(stdout.read().decode())

# Check resources.arsc size and content
print("=== Resources check ===")
stdin, stdout, stderr = ssh.exec_command(
    'cd /root/.sop && python3 -c "'
    'import zipfile; z=zipfile.ZipFile(\"/tmp/test_plain.apk\"); '
    'print(\"entries:\", len(z.infolist())); '
    'for e in z.infolist(): print(f\"  {e.filename} ({e.file_size})\"); '
    'z.close()"'
)
print(stdout.read().decode())

ssh.close()
