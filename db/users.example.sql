-- Run once by hand as root: sudo mariadb
-- Replace <password> with the real one, which is kept only in /etc/viikko5/viikko5.env.
CREATE USER IF NOT EXISTS 'viikko5app'@'localhost' IDENTIFIED BY '<password>';
-- Only what the app needs: read the history and add new messages.
GRANT SELECT, INSERT ON viikko5chat.messages TO 'viikko5app'@'localhost';
FLUSH PRIVILEGES;
SHOW GRANTS FOR 'viikko5app'@'localhost';
