#!/bin/bash
cd /root/.sop/hathixfud-bot
export LD_LIBRARY_PATH=/android-sdk/build-tools/34.0.0/lib64
exec /usr/bin/python3 hathixfud_bot.py
