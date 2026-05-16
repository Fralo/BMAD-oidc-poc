-- Application schema for resource-server. Runs on first MariaDB init only.
-- Database name must match compose/.env DATABASE_NAME (default: testdb).
USE `testdb`;

CREATE TABLE IF NOT EXISTS DUMMY (
  id INT AUTO_INCREMENT PRIMARY KEY,
  uuid VARCHAR(36) NOT NULL,
  name VARCHAR(255) NOT NULL,
  description VARCHAR(255) NULL,
  UNIQUE KEY uk_dummy_uuid (uuid),
  KEY ix_dummy_uuid (uuid)
);
