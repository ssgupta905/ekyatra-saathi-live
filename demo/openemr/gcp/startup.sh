#!/bin/bash
# Startup script for the Compute Engine VM that runs the hospital systems: OpenEMR
# (with MariaDB) and the HAPI FHIR server (with Postgres). Stock images, nothing
# of ours inside them (OpenEMR as in demo/openemr/docker-compose.yml). Idempotent: safe to run again on every boot.
#
# The admin password is NOT in this file. It is read from instance metadata `oe-pass`
# if one was given; otherwise the VM generates a random one on first boot and keeps
# it in /root/openemr-admin-password.txt (read it over SSH: sudo cat that file).
set -euo pipefail

meta() { curl -fs -H 'Metadata-Flavor: Google' "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1" || true; }
if [ -s /root/openemr-admin-password.txt ]; then
  OE_PASS="$(cat /root/openemr-admin-password.txt)"          # keep the same one across reboots
else
  OE_PASS="$(meta oe-pass)"
  [ -n "$OE_PASS" ] || OE_PASS="$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | cut -c1-16)"
fi

# HAPI's own database password: generated here, kept on the VM, never on the internet.
umask 077
if [ -s /root/hapi-db-password.txt ]; then
  HAPI_DB_PASS="$(cat /root/hapi-db-password.txt)"
else
  HAPI_DB_PASS="$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | cut -c1-16)"
  printf '%s\n' "${HAPI_DB_PASS}" > /root/hapi-db-password.txt
fi

# At first boot Google's Ops Agent is installed by apt too and holds the package lock for a
# minute or two; without this the install below fails with "Could not get lock" (exit 100).
# The setting applies to every apt-get, including the ones Docker's installer runs.
export DEBIAN_FRONTEND=noninteractive
echo 'DPkg::Lock::Timeout "600";' > /etc/apt/apt.conf.d/99saathi-lock-timeout

if ! command -v docker >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y curl ca-certificates
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

mkdir -p /opt/openemr && cd /opt/openemr

cat > readonly-user.sql <<'SQL'
-- The only account EKYATRA uses against this database, and it can only read.
CREATE USER IF NOT EXISTS 'saathi_ro'@'%' IDENTIFIED BY 'saathi_ro';
GRANT SELECT ON openemr.* TO 'saathi_ro'@'%';
FLUSH PRIVILEGES;
SQL
chmod 644 readonly-user.sql   # MariaDB's init reads it as another user, despite the umask

# The database port is bound to the VM itself and never published to the internet.
cat > docker-compose.yml <<YML
services:
  mysql:
    image: mariadb:11
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: root
    ports: ["127.0.0.1:3307:3306"]
    volumes:
      - oedb:/var/lib/mysql
      - ./readonly-user.sql:/docker-entrypoint-initdb.d/10-saathi-readonly.sql:ro
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 10s
      timeout: 5s
      retries: 12
  openemr:
    image: openemr/openemr:flex
    restart: unless-stopped
    depends_on:
      mysql:
        condition: service_healthy
    ports: ["8300:80"]
    environment:
      MYSQL_HOST: mysql
      MYSQL_ROOT_PASS: root
      MYSQL_USER: openemr
      MYSQL_PASS: openemr
      OE_USER: admin
      OE_PASS: "${OE_PASS}"
  # The HAPI FHIR server, the district hospital's system, on Postgres. It is read
  # through the same FHIR connector as any other conformant server.
  hapi-db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_USER: hapi
      POSTGRES_PASSWORD: "${HAPI_DB_PASS}"
      POSTGRES_DB: hapi
    volumes:
      - hapidb:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hapi"]
      interval: 10s
      timeout: 5s
      retries: 12
  hapi:
    image: hapiproject/hapi:latest
    restart: unless-stopped
    depends_on:
      hapi-db:
        condition: service_healthy
    ports: ["8080:8080"]
    environment:
      SPRING_DATASOURCE_URL: jdbc:postgresql://hapi-db:5432/hapi
      SPRING_DATASOURCE_USERNAME: hapi
      SPRING_DATASOURCE_PASSWORD: "${HAPI_DB_PASS}"
      SPRING_DATASOURCE_DRIVER_CLASS_NAME: org.postgresql.Driver
      SPRING_JPA_PROPERTIES_HIBERNATE_DIALECT: ca.uhn.fhir.jpa.model.dialect.HapiFhirPostgresDialect
      HAPI_FHIR_FHIR_VERSION: R4
      HAPI_FHIR_ALLOW_EXTERNAL_REFERENCES: "true"
volumes:
  oedb:
  hapidb:
YML

# The password file is readable by root only, for whoever needs to retrieve it.
umask 077
printf '%s\n' "${OE_PASS}" > /root/openemr-admin-password.txt

docker compose up -d
