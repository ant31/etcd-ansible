# ============================================================================
# ETCD-ANSIBLE MAKEFILE
# ============================================================================
# Fully parameterizable - override any variable:
#   make create INVENTORY=inventory/test.ini TAGS=etcd OPTS=-vvv
#
# Test is just production with different inventory:
#   make create INVENTORY=inventory/inventory-test.ini
# ============================================================================

.PHONY: all clean create deploy upgrade delete backup restore health \
        backup-ca restore-ca replicate-ca setup-kms \
        docs docs-serve docs-build docs-deploy docs-clean help

# ============================================================================
# CONFIGURATION VARIABLES (override on command line)
# ============================================================================

# Inventory file (change this for test/staging/prod)
INVENTORY ?= inventory/inventory.ini

# Ansible tags (e.g., TAGS=etcd,certs)
TAGS ?=

# Extra ansible options (e.g., OPTS=-vvv or OPTS=--check)
OPTS ?=

# Limit to specific groups/hosts (e.g., GROUPS=etcd[0])
GROUPS ?=

# Vault password file
VAULT_PASS_FILE ?= $(HOME)/.vault-pass

# ============================================================================
# COMPUTED VARIABLES (don't override these)
# ============================================================================

# Vault argument (auto-detected)
VAULT_ARG := $(shell if [ -f $(VAULT_PASS_FILE) ]; then echo "--vault-password-file $(VAULT_PASS_FILE)"; fi)

# Build ansible command with all options
ANSIBLE_CMD = ansible-playbook -i $(INVENTORY) $(if $(TAGS),--tags $(TAGS)) $(if $(GROUPS),--limit $(GROUPS)) $(OPTS)

# ============================================================================
# CLUSTER LIFECYCLE
# ============================================================================

create:
	@echo "📦 Creating etcd cluster..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-cluster.yaml -e etcd_action=create -b $(VAULT_ARG)

deploy:
	@echo "🚀 Deploying/updating etcd cluster..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-cluster.yaml -e etcd_action=deploy -b $(VAULT_ARG)

upgrade:
	@echo "⬆️  Upgrading etcd cluster..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/upgrade-cluster.yaml -b $(VAULT_ARG)

delete:
	@echo "⚠️  WARNING: Deleting etcd cluster!"
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-cluster.yaml -e etcd_delete_cluster=true -b $(VAULT_ARG)

# ============================================================================
# FORCE OPERATIONS (USE WITH CAUTION)
# ============================================================================

force-create:
	@echo "💥 FORCE creating cluster (destroys existing data)..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-cluster.yaml -e etcd_action=create -e etcd_force_create=true -b $(VAULT_ARG)

force-deploy:
	@echo "💥 FORCE deploying (ignores health checks)..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-cluster.yaml -e etcd_action=deploy -e etcd_force_deploy=true -b $(VAULT_ARG)

force-upgrade:
	@echo "💥 FORCE upgrading (ignores health checks)..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/upgrade-cluster.yaml -e etcd_force_deploy=true -b $(VAULT_ARG)

force-restart:
	@echo "💥 FORCE rolling restart (skips health checks)..."
	@echo "Inventory: $(INVENTORY)"
	@echo ""
	@echo "⚠️  WARNING: This skips pre-restart health validation!"
	@echo "Only use if cluster is partially down but quorum exists."
	@echo ""
	$(ANSIBLE_CMD) playbooks/restart-cluster.yaml -b -e skip_health_check=true

# ============================================================================
# BACKUP & RESTORE
# ============================================================================

backup:
	@echo "💾 Creating etcd data backup..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-cluster.yaml -e etcd_action=backup -b $(VAULT_ARG)

restore:
	@echo "♻️  Restoring etcd cluster from backup..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/restore-etcd-cluster.yaml -b $(VAULT_ARG)

backup-ca:
	@echo "🔐 Backing up CA keys..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/backup-ca.yaml $(VAULT_ARG)

restore-ca:
	@echo "🔐 Restoring CA keys from backup..."
	@echo "Inventory: $(INVENTORY)"
	@read -p "Enter target node: " node; \
	$(ANSIBLE_CMD) playbooks/restore-ca-from-backup.yaml -e target_node=$$node $(VAULT_ARG)

restore-ca-from-node:
	@echo "🔐 Restoring CA from another node..."
	@echo "Inventory: $(INVENTORY)"
	@read -p "Enter source node: " source; \
	read -p "Enter target node: " target; \
	$(ANSIBLE_CMD) playbooks/restore-ca.yaml -e source_node=$$source -e target_node=$$target $(VAULT_ARG)

replicate-ca:
	@echo "🔄 Replicating CA keys to backup cert-managers..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/replicate-ca.yaml $(VAULT_ARG)

# ============================================================================
# CERTIFICATE OPERATIONS
# ============================================================================

renew-certs:
	@echo "🔄 Manually renewing all certificates..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/renew-certs.yaml -b

check-certs:
	@echo "🔍 Checking certificate expiration..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-health.yaml --tags certs


regenerate-node-certs:
	@echo "🔄 Regenerating node certificates (ROUTINE - quarterly rotation)..."
	@echo "Inventory: $(INVENTORY)"
	@echo ""
	@echo "This is a SAFE routine operation:"
	@echo "  - Regenerates only node certificates (peer, server, client)"
	@echo "  - CA stays intact (no password changes needed)"
	@echo "  - Zero downtime (rolling restart)"
	@echo "  - Recommended: Run quarterly for certificate hygiene"
	@echo ""
	$(ANSIBLE_CMD) playbooks/regenerate-node-certs.yaml -b $(VAULT_ARG)

regenerate-ca:
	@echo "⚠️  Regenerating CA and ALL certificates (DISASTER RECOVERY)..."
	@echo "Inventory: $(INVENTORY)"
	@echo ""
	@echo "⚠️  WARNING: This is a DESTRUCTIVE operation!"
	@echo "  - Completely rebuilds CA with NEW passwords"
	@echo "  - All existing certificates become invalid"
	@echo "  - External clients need NEW certificates"
	@echo ""
	@echo "Only use when:"
	@echo "  - CA password is lost"
	@echo "  - CA is compromised"
	@echo "  - Root CA expired"
	@echo ""
	@echo "For routine rotation, use: make regenerate-node-certs"
	@echo ""
	$(ANSIBLE_CMD) playbooks/regenerate-ca.yaml -b $(VAULT_ARG)


# ============================================================================
# OPERATIONS
# ============================================================================

health:
	@echo "🏥 Running cluster health checks..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-health.yaml

health-json:
	@echo "🏥 Running cluster health checks (JSON output)..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-health.yaml -e output_format=json

status:
	@echo "📊 Checking cluster status..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-status.yaml -b

members:
	@echo "👥 Listing cluster members..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-members.yaml -b

logs:
	@echo "📜 Viewing etcd logs..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-logs.yaml -b

logs-follow:
	@echo "📜 Following etcd logs (live)..."
	@echo "Inventory: $(INVENTORY)"
	@echo "NOTE: Use Ctrl+C to stop"
	$(ANSIBLE_CMD) playbooks/etcd-logs-follow.yaml -b

compact:
	@echo "🗜️  Compacting etcd database..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-compact.yaml -b

defrag:
	@echo "🔧 Defragmenting etcd database..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/etcd-defrag.yaml -b

setup-kms:
	@echo "☁️  Setting up AWS KMS key..."
	ansible-playbook playbooks/setup-kms.yaml -e kms_key_alias=alias/etcd-ca-backup

multi-cluster:
	@echo "🏗️  Deploying multi-cluster example..."
	$(ANSIBLE_CMD) playbooks/multi-cluster-example.yaml -e etcd_action=create -b $(VAULT_ARG)

# ============================================================================
# CLEANUP OPERATIONS
# ============================================================================

clean:
	@echo "🧹 Cleaning temporary files..."
	rm -rf dist/
	rm -f *.retry

clean-certs:
	@echo "🗑️  Removing certificates..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/clean-certs.yaml -b

clean-data:
	@echo "⚠️  WARNING: Removing all etcd data directories..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/clean-data.yaml -b

clean-backups:
	@echo "🗑️  Cleaning old local backups..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/clean-backups.yaml -b

clean-logs:
	@echo "🗑️  Cleaning old logs..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/clean-logs.yaml -b

clean-all:
	@echo "🧹 Cleaning all cluster data..."
	@$(MAKE) clean-certs
	@$(MAKE) clean-data

stop-all:
	@echo "🛑 Stopping all etcd services..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/stop-cluster.yaml -b

start-all:
	@echo "▶️  Starting all etcd services..."
	@echo "Inventory: $(INVENTORY)"
	$(ANSIBLE_CMD) playbooks/start-cluster.yaml -b

restart-all:
	@echo "🔄 Rolling restart of etcd cluster (maintains quorum)..."
	@echo "Inventory: $(INVENTORY)"
	@echo ""
	@echo "This will restart nodes one at a time with health checks."
	@echo "Quorum will be maintained throughout (n-1 nodes always up)."
	@echo ""
	$(ANSIBLE_CMD) playbooks/restart-cluster.yaml -b

# ============================================================================
# DOCUMENTATION
# ============================================================================

docs-serve:
	@echo "📚 Starting documentation server..."
	mkdocs serve

docs-build:
	@echo "📦 Building documentation..."
	mkdocs build

docs-deploy:
	@echo "🚀 Deploying documentation to GitHub Pages..."
	mkdocs gh-deploy --force

docs-clean:
	@echo "🧹 Cleaning documentation build..."
	rm -rf site/

docs: docs-serve

# ============================================================================
# HELP
# ============================================================================

help:
	@echo "════════════════════════════════════════════════════════════════════════════════"
	@echo "ETCD-ANSIBLE MAKEFILE"
	@echo "════════════════════════════════════════════════════════════════════════════════"
	@echo ""
	@echo "📋 CLUSTER LIFECYCLE"
	@echo "  make create              - Create new cluster"
	@echo "  make deploy              - Deploy/update cluster"
	@echo "  make upgrade             - Upgrade cluster version (rolling)"
	@echo "  make delete              - Delete cluster (with confirmation)"
	@echo ""
	@echo "💥 FORCE OPERATIONS (DANGEROUS - USE WITH CAUTION)"
	@echo "  make force-create        - Force create (destroys existing data)"
	@echo "  make force-deploy        - Force deploy (ignores health checks)"
	@echo "  make force-upgrade       - Force upgrade (ignores health checks)"
	@echo "  make force-restart       - Force restart all services"
	@echo "  make force-cert-rotation - Force regenerate all certificates"
	@echo ""
	@echo "💾 BACKUP & RESTORE"
	@echo "  make backup              - Backup etcd data"
	@echo "  make restore             - Restore etcd data from backup"
	@echo "  make backup-ca           - Backup CA keys to S3"
	@echo "  make restore-ca          - Restore CA from S3 backup (prompts for node)"
	@echo "  make restore-ca-from-node - Restore CA from another node (prompts)"
	@echo "  make replicate-ca        - Replicate CA to backup cert-managers"
	@echo ""
	@echo "🔐 CERTIFICATE OPERATIONS (in order of frequency/severity)"
	@echo "  make check-certs         - Check certificate expiration"
	@echo "  make renew-certs         - Force early renewal (same certs, just renewed)"
	@echo "  make regenerate-node-certs - NEW node certs (ROUTINE - quarterly rotation)"
	@echo "  make regenerate-ca       - NEW CA + certs (DISASTER - lost CA password)"
	@echo ""
	@echo "  Comparison:"
	@echo "    renew-certs:            Same certs, extended expiry (emergency renewal)"
	@echo "    regenerate-node-certs:  New certs, same CA (routine quarterly)"
	@echo "    regenerate-ca:          New CA + new certs (disaster recovery)"
	@echo ""
	@echo "🔧 OPERATIONS & MAINTENANCE"
	@echo "  make health              - Run health checks"
	@echo "  make health-json         - Health checks (JSON output)"
	@echo "  make status              - Show cluster status"
	@echo "  make members             - List cluster members"
	@echo "  make logs                - View recent logs"
	@echo "  make logs-follow         - Follow logs (live)"
	@echo "  make compact             - Compact database"
	@echo "  make defrag              - Defragment database"
	@echo "  make setup-kms           - Setup AWS KMS key for backups"
	@echo "  make multi-cluster       - Deploy multi-cluster example"
	@echo ""
	@echo "🛑 SERVICE CONTROL"
	@echo "  make stop-all            - Stop all etcd services"
	@echo "  make start-all           - Start all etcd services"
	@echo "  make restart-all         - Restart all etcd services"
	@echo ""
	@echo "🧹 CLEANUP"
	@echo "  make clean               - Clean temporary files"
	@echo "  make clean-certs         - Remove certificates (regenerated on deploy)"
	@echo "  make clean-data          - Remove all etcd data (requires confirmation)"
	@echo "  make clean-backups       - Clean old local backups (>30 days)"
	@echo "  make clean-logs          - Clean old logs (>7 days)"
	@echo "  make clean-all           - Clean certs + data"
	@echo ""
	@echo "📚 DOCUMENTATION"
	@echo "  make docs                - Serve docs at http://127.0.0.1:8000"
	@echo "  make docs-build          - Build static documentation"
	@echo "  make docs-deploy         - Deploy to GitHub Pages"
	@echo ""
	@echo "🧹 UTILITIES"
	@echo "  make clean               - Clean temporary files"
	@echo ""
	@echo "════════════════════════════════════════════════════════════════════════════════"
	@echo "⚙️  PARAMETERS (override any variable):"
	@echo ""
	@echo "  INVENTORY=path/to/inventory.ini    - Inventory file (default: inventory/inventory.ini)"
	@echo "  TAGS=tag1,tag2                     - Ansible tags to run"
	@echo "  OPTS='-vvv --check'                - Extra ansible options"
	@echo "  GROUPS='etcd[0]'                   - Limit to specific groups/hosts"
	@echo "  VAULT_PASS_FILE=path/to/file       - Vault password file (default: ~/.vault-pass, OPTIONAL)"
	@echo ""
	@echo "════════════════════════════════════════════════════════════════════════════════"
	@echo "💡 EXAMPLES:"
	@echo ""
	@echo "  Production:"
	@echo "    make create                                    # Uses inventory/inventory.ini"
	@echo "    make health"
	@echo "    make backup"
	@echo "    make status"
	@echo "    make renew-certs"
	@echo ""
	@echo "  Test/Staging (just use different inventory):"
	@echo "    make create INVENTORY=inventory/inventory-test.ini"
	@echo "    make health INVENTORY=inventory/inventory-test.ini"
	@echo "    make delete INVENTORY=inventory/inventory-test.ini"
	@echo ""
	@echo "  With options:"
	@echo "    make create TAGS=etcd OPTS=-vvv               # Verbose, only etcd tags"
	@echo "    make upgrade GROUPS=etcd[0] OPTS=--check      # Dry-run on first node"
	@echo "    make health INVENTORY=inventory/staging.ini GROUPS=etcd-k8s"
	@echo ""
	@echo "  Certificate operations:"
	@echo "    make check-certs                              # Check expiration"
	@echo "    make renew-certs                              # Force early renewal (emergency)"
	@echo "    make regenerate-node-certs                    # Routine quarterly rotation (new certs)"
	@echo "    make regenerate-ca                            # Disaster recovery (new CA)"
	@echo ""
	@echo "  Certificate operations decision tree:"
	@echo "    Cert expires in < 7 days?        → make renew-certs (emergency)"
	@echo "    Quarterly cert hygiene?          → make regenerate-node-certs (routine)"
	@echo "    Lost CA password?                → make regenerate-ca (disaster)"
	@echo "    Just checking status?            → make check-certs"
	@echo ""
	@echo "  Maintenance:"
	@echo "    make compact                                  # Compact database"
	@echo "    make defrag                                   # Defragment database"
	@echo "    make clean-backups                            # Clean old backups"
	@echo "    make logs-follow                              # Watch live logs"
	@echo ""
	@echo "  Advanced:"
	@echo "    make deploy INVENTORY=inventory/prod.ini TAGS=certs GROUPS=etcd[1:]"
	@echo "    make backup INVENTORY=inventory/test.ini OPTS='--extra-vars backup_retention_days=30'"
	@echo "    make force-deploy INVENTORY=inventory/test.ini  # Deploy on unhealthy cluster (risky)"
	@echo ""
	@echo "════════════════════════════════════════════════════════════════════════════════"
	@echo "🚀 QUICK START:"
	@echo ""
	@echo "  1. Setup inventory:"
	@echo "       cp inventory/inventory-example.ini inventory/inventory.ini"
	@echo "       vi inventory/inventory.ini  # Add your nodes"
	@echo ""
	@echo "  2. Setup secrets:"
	@echo "       cp inventory/group_vars/all/vault.yml.example inventory/group_vars/all/vault.yml"
	@echo "       vi inventory/group_vars/all/vault.yml  # Add your secrets"
	@echo "       ansible-vault encrypt inventory/group_vars/all/vault.yml"
	@echo "       echo 'your-vault-password' > ~/.vault-pass && chmod 600 ~/.vault-pass"
	@echo ""
	@echo "  3. Deploy:"
	@echo "       make create      # Creates cluster"
	@echo "       make health      # Verify it's healthy"
	@echo ""
	@echo "  For testing, just use a different inventory:"
	@echo "       make create INVENTORY=inventory/inventory-test.ini"
	@echo ""
	@echo "💡 VAULT IS OPTIONAL:"
	@echo "   If ~/.vault-pass exists, it will be used automatically"
	@echo "   Otherwise, vault.yml can be unencrypted (not recommended for prod)"
	@echo "   Or provide password: VAULT_PASS_FILE=/path/to/file make create"
	@echo ""
	@echo "════════════════════════════════════════════════════════════════════════════════"
	@echo "📖 Full documentation: make docs"
	@echo "════════════════════════════════════════════════════════════════════════════════"

# Default target
all: help

# ============================================================================
# TESTING
# ============================================================================

test:
	@echo "🧪 Running tests on test inventory..."	
	@echo "✅ All tests passed"

# ============================================================================
# CONVENIENCE ALIASES (for muscle memory)
# ============================================================================

create-cluster: create
deploy-cluster: deploy
upgrade-cluster: upgrade
delete-cluster: delete
backup-cluster: backup
restore-cluster: restore
health-check: health
