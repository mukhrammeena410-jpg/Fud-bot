#!/usr/bin/env python3
"""Fix the wrapper template's AndroidManifest.xml to include versionCode and versionName."""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# Check the wrapper manifest xmltree to understand its structure
cmd = 'aapt dump xmltree /tmp/test_kb.apk AndroidManifest.xml 2>&1'
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== XMLTREE ===")
print(stdout.read().decode())

ssh.close()
