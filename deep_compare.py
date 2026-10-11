#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# 1. Build with ORIGINAL bot's protect_apk.py
print("=== Building with ORIGINAL bot ===")
stdin, stdout, stderr = ssh.exec_command(
    'cd /root/.sop/hathixfud-bot && python3 protect_apk.py --apk /tmp/test_input.apk -o /tmp/test_original.apk 2>&1',
    timeout=120)
print(stdout.read().decode())
print(stderr.read().decode())

# 2. Check original APK
print("=== Original APK aapt ===")
stdin, stdout, stderr = ssh.exec_command('aapt dump badging /tmp/test_original.apk 2>&1 | head -5')
print(stdout.read().decode())

# 3. Build with KB bot's protect_apk.py
print("=== Building with KB bot ===")
stdin, stdout, stderr = ssh.exec_command(
    'cd /root/.sop/hathixfud-bot-kb && python3 protect_apk.py --apk /tmp/test_input.apk -o /tmp/test_kb.apk 2>&1',
    timeout=120)
print(stdout.read().decode())
print(stderr.read().decode())

# 4. Check KB APK
print("=== KB APK aapt ===")
stdin, stdout, stderr = ssh.exec_command('aapt dump badging /tmp/test_kb.apk 2>&1 | head -5')
print(stdout.read().decode())

# 5. Compare file sizes
print("=== File sizes ===")
stdin, stdout, stderr = ssh.exec_command('ls -la /tmp/test_original.apk /tmp/test_kb.apk /tmp/test_input.apk 2>&1')
print(stdout.read().decode())

# 6. Compare ZIP entries
print("=== ZIP entry count ===")
stdin, stdout, stderr = ssh.exec_command('cd /root/.sop && python3 -c "import zipfile; o=zipfile.ZipFile(\"/tmp/test_original.apk\"); k=zipfile.ZipFile(\"/tmp/test_kb.apk\"); print(f\"original: {len(o.infolist())} entries, kb: {len(k.infolist())} entries\"); o.close(); k.close()"')
print(stdout.read().decode())

# 7. Compare resources.arsc
print("=== resources.arsc comparison ===")
stdin, stdout, stderr = ssh.exec_command('cd /root/.sop && python3 -c "import zipfile; o=zipfile.ZipFile(\"/tmp/test_original.apk\"); k=zipfile.ZipFile(\"/tmp/test_kb.apk\"); oa=o.read(\"resources.arsc\"); ka=k.read(\"resources.arsc\"); print(f\"original arsc: {len(oa)} bytes, kb arsc: {len(ka)} bytes, same: {oa==ka}\"); o.close(); k.close()"')
print(stdout.read().decode())

# 8. Compare AndroidManifest.xml
print("=== AndroidManifest.xml comparison ===")
stdin, stdout, stderr = ssh.exec_command('cd /root/.sop && python3 -c "import zipfile; o=zipfile.ZipFile(\"/tmp/test_original.apk\"); k=zipfile.ZipFile(\"/tmp/test_kb.apk\"); oa=o.read(\"AndroidManifest.xml\"); ka=k.read(\"AndroidManifest.xml\"); print(f\"original manifest: {len(oa)} bytes, kb manifest: {len(ka)} bytes, same: {oa==ka}\"); o.close(); k.close()"')
print(stdout.read().decode())

# 9. Compare classes.dex
print("=== classes.dex comparison ===")
stdin, stdout, stderr = ssh.exec_command('cd /root/.sop && python3 -c "import zipfile; o=zipfile.ZipFile(\"/tmp/test_original.apk\"); k=zipfile.ZipFile(\"/tmp/test_kb.apk\"); oa=o.read(\"classes.dex\"); ka=k.read(\"classes.dex\"); print(f\"original dex: {len(oa)} bytes, kb dex: {len(ka)} bytes, same: {oa==ka}\"); o.close(); k.close()"')
print(stdout.read().decode())

# 10. Compare payload
print("=== Payload comparison ===")
stdin, stdout, stderr = ssh.exec_command('cd /root/.sop && python3 -c "import zipfile; o=zipfile.ZipFile(\"/tmp/test_original.apk\"); k=zipfile.ZipFile(\"/tmp/test_kb.apk\"); oa=o.read(\"assets/nvcgehin\"); ka=k.read(\"assets/nvcgehin\"); print(f\"original payload: {len(oa)} bytes, kb payload: {len(ka)} bytes, same: {oa==ka}\"); o.close(); k.close()"')
print(stdout.read().decode())

ssh.close()
