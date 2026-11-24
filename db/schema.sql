-- Week 5 chat database. Safe to run many times (applied by deploy/deploy.sh as root).
CREATE DATABASE IF NOT EXISTS viikko5chat
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE viikko5chat;

CREATE TABLE IF NOT EXISTS messages (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_id  CHAR(36)        NOT NULL,             -- random UUID from the browser cookie
  role        ENUM('user', 'assistant') NOT NULL,
  content     TEXT            NOT NULL,
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_session (session_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
