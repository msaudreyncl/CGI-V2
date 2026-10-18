-- ============================================================
-- CGI — Seed Data
-- Run AFTER schema.sql
-- ============================================================

USE cgi_db;

-- Default cooperative
INSERT INTO cooperatives (name, location, contact)
VALUES ('Default Cooperative', 'Philippines', NULL);

-- Default admin user  (password: Admin@1234 — CHANGE BEFORE PRODUCTION)
-- bcrypt hash of "Admin@1234" (generated and verified)
INSERT INTO users (id, name, email, password_hash, role)
VALUES (
    1,
    'System Admin',
    'admin@cgi.local',
    '$2b$12$5mPTIlXBuooTeIl6OGFlC.DrHKNqZc5fYvrPnXUorizqd4XFRg7ru',
    'admin'
);

-- Default pricing multipliers
INSERT INTO pricing_config (grade, multiplier) VALUES
    ('extra_class', 1.0000),
    ('class_i',     0.8500),
    ('class_ii',    0.7000);
