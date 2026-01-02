#!/bin/bash

# 1. 啟動 ngrok 的 tmux 會話
# -d 代表在背景執行，-s 是會話名稱
tmux new-session -d -s dodora_ngrok
tmux send-keys -t dodora_ngrok "ngrok http --domain=unintoned-hamza-refulgently.ngrok-free.dev 5000 " C-m

# 2. 啟動 Python 程式的 tmux 會話
tmux new-session -d -s dodora_bot
tmux send-keys -t dodora_bot "cd /home/chiu/Chiu/dodora" C-m
tmux send-keys -t dodora_bot "source ~/miniconda3/bin/activate linebot" C-m
tmux send-keys -t dodora_bot "python dodora.py" C-m

exit 0