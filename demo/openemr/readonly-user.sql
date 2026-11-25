-- The only account EKYATRA uses against this database, and it can only read.
--
-- The connector's read-only claim is defended in three places, deliberately:
-- every SQL string in `adapters/hospital/openemr_db.py` is a SELECT (a test
-- parses the module and fails otherwise), the session is opened `SET SESSION
-- TRANSACTION READ ONLY`, and this grant means even a bug could not write.
--
-- Change the password before any deployment that is not a laptop.
CREATE USER IF NOT EXISTS 'saathi_ro'@'%' IDENTIFIED BY 'saathi_ro';
GRANT SELECT ON openemr.* TO 'saathi_ro'@'%';
FLUSH PRIVILEGES;
