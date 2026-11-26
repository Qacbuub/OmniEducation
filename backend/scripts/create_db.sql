-- Creates the OmniEducation database user and database (safe to run again).
-- CREATEDB lets the test suite create its temporary test database.
SELECT 'CREATE ROLE omniedu LOGIN PASSWORD ''omniedu'' CREATEDB'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'omniedu')\gexec
SELECT 'CREATE DATABASE omniedu OWNER omniedu ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'omniedu')\gexec
