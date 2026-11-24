# Server evidence

Paste command output from the server into these files (remove any secrets first).
The documentation page `/viikko5/docs` shows them automatically after the next deployment.

| File | Command(s) |
|---|---|
| `systemctl-status.txt` | `systemctl status viikko5 --no-pager` and `systemctl show viikko5 -p User -p Group` |
| `ls-l.txt` | `sudo ls -l /opt/viikko5 /opt/viikko5/app /etc/viikko5` |
| `grants.txt` | `sudo mariadb -e "SHOW GRANTS FOR 'viikko5app'@'localhost';"` |
| `ollama-free.txt` | `ollama list`, `free -h` and `df -h /` with the model loaded |
| `ss-ltnp.txt` | `sudo ss -ltnp` |
