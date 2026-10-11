#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

sftp = ssh.open_sftp()
sftp.put(r'C:\Users\Lucky\OneDrive\Desktop\Advance Fud bot\hathixfud\patch_manifest_standalone.py',
         '/tmp/patch_manifest_standalone.py')
sftp.close()

stdin, stdout, stderr = ssh.exec_command('python3 /tmp/patch_manifest_standalone.py 2>&1', timeout=120)
print(stdout.read().decode())
print(stderr.read().decode())

ssh.close()
