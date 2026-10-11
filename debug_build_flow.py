#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

cmds = [
    "grep -n 'Building\|_run_protect\|protect_apk\|build_apk\|icon_handler\|STEP_BUILD\|send_document\|step.*icon\|in_session\|apk_path\|session.*build\|label.*step\|icon.*step' /root/.sop/hathixfud-bot-kb/hathixfud_bot.py | head -50",
]

for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(out)
    if err:
        print("ERR:", err)

ssh.close()
