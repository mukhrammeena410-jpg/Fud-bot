#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('162.19.81.122', port=20056, username='root', password='yfoTsKjtY8UgVUsY', timeout=15)

# Clear wrapper patterns from KB
stdin, stdout, stderr = ssh.exec_command("sqlite3 /root/.sop/hathixfud-bot-kb/hathixfud_bot.db \"DELETE FROM apk_knowledge WHERE category='wrapper';\"")
print("Cleared wrapper patterns from KB")

# Check remaining patterns
stdin, stdout, stderr = ssh.exec_command("sqlite3 /root/.sop/hathixfud-bot-kb/hathixfud_bot.db \"SELECT category, COUNT(*) FROM apk_knowledge GROUP BY category;\"")
print("Remaining KB patterns:")
print(stdout.read().decode())

ssh.close()
