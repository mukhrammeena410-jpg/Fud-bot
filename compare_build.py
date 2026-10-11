#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# Get the full diff between original and KB protect_apk.py - just the build() function
cmd = """
cd /root/.sop && python3 -c "
import ast, textwrap

# Parse both files
with open('hathixfud-bot/protect_apk.py') as f:
    orig = f.read()
with open('hathixfud-bot-kb/protect_apk.py') as f:
    kb = f.read()

# Find differences in build function
orig_lines = orig.split('\n')
kb_lines = kb.split('\n')

# Simple line-by-line diff for build()
in_build_orig = False
in_build_kb = False
for i, line in enumerate(orig_lines):
    if 'def build(' in line:
        in_build_orig = True
    elif in_build_orig and line and not line[0].isspace() and 'def ' in line:
        in_build_orig = False

for i, line in enumerate(kb_lines):
    if 'def build(' in line:
        in_build_kb = True
    elif in_build_kb and line and not line[0].isspace() and 'def ' in line:
        in_build_kb = False
"
"""

# Simpler approach - just get the key differences
cmds = [
    "grep -n 'def build\|def unpack\|def pack\|version_bump\|VERSION_OFFSET\|zipalign\|apksigner\|sign\|OLD_PKG\|icon_path\|icon.*aapt' /root/.sop/hathixfud-bot/protect_apk.py",
    "grep -n 'def build\|def unpack\|def pack\|version_bump\|VERSION_OFFSET\|zipalign\|apksigner\|sign\|OLD_PKG\|icon_path\|icon.*aapt' /root/.sop/hathixfud-bot-kb/protect_apk.py",
]

for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    print(f"=== {cmd[:50]}... ===")
    print(stdout.read().decode())
    print()

ssh.close()
