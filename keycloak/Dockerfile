# keycloak/Dockerfile
# Thin wrapper around the official Keycloak image that bakes the version-controlled
# realm-as-code into the container so `docker compose up keycloak` requires zero
# manual configuration. The realm file is placed under /opt/keycloak/data/import/
# which is where `start-dev --import-realm` (and `start --import-realm --optimized`)
# look for realm JSON files at boot.
#
# Mode: this educational project uses `start-dev` over http://localhost. The
# prod-mode alternative is `start --import-realm --optimized`, which additionally
# requires running `kc.sh build` in a builder stage; that's out of scope per
# architecture I3.
#
# Pinned to Keycloak 26.0 (stable line as of 2026-05-14). Bump to a later 26.x
# patch is safe; major-version bumps need a realm-JSON compatibility check.
#
# Note: the official 26.0 image ships without curl, wget, or any package
# manager (microdnf/dnf/yum/apt are all absent). The compose-level healthcheck
# therefore uses bash's `/dev/tcp` virtual device (bash, grep, printf are
# present) rather than installing a new tool here.
FROM quay.io/keycloak/keycloak:26.0

COPY realm-bmad-books.json /opt/keycloak/data/import/realm-bmad-books.json

# `KC_HEALTH_ENABLED=true` (set on the compose service) exposes /health/ready
# on management port 9000; KC_HOSTNAME=localhost on the compose service tells
# Keycloak to emit http://localhost:8080 URLs in issuer/redirect responses.
CMD ["start-dev", "--import-realm"]
