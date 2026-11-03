-- Runs once, when the forgehub_test_pgdata volume is first initialized.
-- Every ForgeHub table lives in `company` (app/db/base.py), and the
-- Alembic migrations assume the schema already exists.
CREATE SCHEMA IF NOT EXISTS company AUTHORIZATION forgehub_test;
