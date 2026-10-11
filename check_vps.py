#!/usr/bin/env python3
"""check_vps.py - Verify all tools on VPS"""
import paramiko

HOST = '162.19.81.122'
PORT = 20056
USER = 'root'
PASS = 'yfoTsKjtY8UgVUsY'
BOT_DIR = '/root/.sop/hathixfud-bot-kb'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)
print('[+] Connected to VPS\n')

# System tools
print('=== SYSTEM TOOLS ===')
checks = {
    'Python': 'python3 --version',
    'Java': 'java -version 2>&1 | head -1',
    'aapt': 'aapt version',
    'zipalign': 'zipalign 2>&1 | head -1',
    'apksigner': 'apksigner version',
    'keytool': 'keytool 2>&1 | head -1',
}
for name, cmd in checks.items():
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    status = 'OK' if out and 'not found' not in out.lower() else 'MISSING'
    print(f'  [{status}] {name}: {out}')

# Symlinks
print('\n=== SYMLINKS ===')
stdin, stdout, stderr = ssh.exec_command('ls -la /usr/local/bin/aapt /usr/local/bin/zipalign /usr/local/bin/apksigner 2>&1')
print(stdout.read().decode())

# Pip packages
print('\n=== PIP PACKAGES ===')
stdin, stdout, stderr = ssh.exec_command('pip3 list 2>/dev/null')
pkgs = stdout.read().decode().lower()
required = ['pycryptodome', 'pillow', 'python-telegram-bot', 'httpx', 'python-dotenv', 'schedule']
for pkg in required:
    status = 'OK' if pkg in pkgs else 'MISSING'
    print(f'  [{status}] {pkg}')

# Bot files
print(f'\n=== BOT FILES ({BOT_DIR}) ===')
stdin, stdout, stderr = ssh.exec_command(f'ls -la {BOT_DIR}/')
print(stdout.read().decode())

# Keys
print('\n=== KEYS ===')
stdin, stdout, stderr = ssh.exec_command(f'ls -la {BOT_DIR}/keys/ 2>&1')
print(stdout.read().decode())

# Bot status
print('\n=== BOT STATUS ===')
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hathixfud-bot-kb')
status = stdout.read().decode().strip()
print(f'  Service: {status}')

stdin, stdout, stderr = ssh.exec_command('systemctl is-active hathixfud-bot')
status2 = stdout.read().decode().strip()
print(f'  Original bot: {status2}')

# Android SDK
print('\n=== ANDROID SDK ===')
stdin, stdout, stderr = ssh.exec_command('ls /android-sdk/build-tools/34.0.0/ 2>/dev/null')
tools = stdout.read().decode().strip()
print(f'  Build tools: {tools}')

ssh.close()
print('\n[+] Check complete!')
