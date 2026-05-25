# SHMS Nautobot Stack - Makefile
# ================================
# Thin wrappers around `invoke` tasks.
#
# Usage:
#   make help
#   make promote TAG=main-a5efb51
#   make start
#   make logs

INVOKE := invoke

.PHONY: help
help:
	@echo "SHMS Nautobot Stack"
	@echo ""
	@echo "IMAGE MANAGEMENT:"
	@echo "  make promote TAG=<tag>   - Promote CI-built images to production"
	@echo "  make images              - Show pinned vs running image digests"
	@echo "  make images TAG=<tag>    - Also compare with latest GHCR digests"
	@echo ""
	@echo "STACK CONTROL:"
	@echo "  make start               - Start nautobot/celery stack"
	@echo "  make stop                - Stop nautobot/celery stack"
	@echo "  make restart             - Restart nautobot/celery stack"
	@echo "  make recreate            - Force-recreate all containers"
	@echo "  make ps                  - Show container status"
	@echo "  make logs                - Tail nautobot + celery_worker logs"
	@echo ""
	@echo "VPN CONTROL API:"
	@echo "  make vpn-start           - Start vpn-control-api container"
	@echo "  make vpn-stop            - Stop vpn-control-api container"
	@echo "  make vpn-restart         - Restart vpn-control-api container"
	@echo "  make vpn-logs            - Tail vpn-control-api logs"
	@echo ""
	@echo "NAUTOBOT MANAGEMENT:"
	@echo "  make post-upgrade        - Run nautobot-server post_upgrade"
	@echo "  make migrate             - Run nautobot-server migrate"
	@echo "  make nbshell             - Open nautobot shell_plus"
	@echo "  make cli                 - Open bash in nautobot container"
	@echo "  make createsuperuser     - Create admin superuser"

# ===== IMAGE MANAGEMENT =====
.PHONY: promote
promote:
	@if [ -z "$(TAG)" ]; then \
		echo "Error: TAG is required"; \
		echo "Usage: make promote TAG=main-a5efb51"; \
		exit 1; \
	fi
	$(INVOKE) promote --tag $(TAG)

.PHONY: images
images:
	@if [ -n "$(TAG)" ]; then \
		$(INVOKE) images --tag $(TAG); \
	else \
		$(INVOKE) images; \
	fi

# ===== STACK CONTROL =====
.PHONY: start
start:
	$(INVOKE) start

.PHONY: stop
stop:
	$(INVOKE) stop

.PHONY: restart
restart:
	$(INVOKE) restart

.PHONY: recreate
recreate:
	$(INVOKE) recreate

.PHONY: ps
ps:
	$(INVOKE) ps

.PHONY: logs
logs:
	$(INVOKE) logs

# ===== VPN CONTROL API =====
.PHONY: vpn-start
vpn-start:
	$(INVOKE) vpn-control-start

.PHONY: vpn-stop
vpn-stop:
	$(INVOKE) vpn-control-stop

.PHONY: vpn-restart
vpn-restart:
	$(INVOKE) vpn-control-restart

.PHONY: vpn-logs
vpn-logs:
	$(INVOKE) vpn-control-logs

# ===== NAUTOBOT MANAGEMENT =====
.PHONY: post-upgrade
post-upgrade:
	$(INVOKE) post-upgrade

.PHONY: migrate
migrate:
	$(INVOKE) migrate

.PHONY: nbshell
nbshell:
	$(INVOKE) nbshell

.PHONY: cli
cli:
	$(INVOKE) cli

.PHONY: createsuperuser
createsuperuser:
	$(INVOKE) createsuperuser

# Shortcuts
.PHONY: up down shell
up: start
down: stop
shell: cli

.DEFAULT_GOAL := help
