.PHONY: clean create-cluster upgrade-cluster delete-cluster test test-create test-health test-upgrade test-backup test-delete test-clean test-download docs docs-serve docs-build help

# Production cluster management
clean:
	rm -rf dist/
	rm *.retry

create-cluster:
	ansible-playbook -i inventory.ini etcd.yaml -vv  -b --become-user=root   -e etcd_action=create

upgrade-cluster:
	ansible-playbook -i inventory.ini etcd.yaml -vv  -b --become-user=root   -e etcd_action=upgrade

delete-cluster:
	ansible-playbook -i inventory.ini etcd.yaml -vv  -b --become-user=root   -e etcd_delete_cluster=true

# Test environment targets (use test inventory with production playbooks)
test:
	@echo "🧪 Running basic test: create cluster + health check"
	@$(MAKE) test-create
	@$(MAKE) test-health
	@echo "✅ Basic test passed"

test-all:
	@echo "🧪 Running full test suite: create → backup → upgrade → restore → delete"
	@$(MAKE) test-create
	@$(MAKE) test-health
	@$(MAKE) test-backup
	@$(MAKE) test-upgrade
	@$(MAKE) test-health
	@$(MAKE) test-restore
	@$(MAKE) test-health
	@$(MAKE) test-delete
	@echo "✅ Full test suite completed"

test-create:
	@echo "📦 Creating test cluster..."
	ansible-playbook -i inventory-test.ini playbooks/etcd-cluster.yaml -e etcd_action=create -b --vault-password-file ~/.vault-pass

test-deploy:
	@echo "📦 Deploying/updating test cluster..."
	ansible-playbook -i inventory-test.ini playbooks/etcd-cluster.yaml -e etcd_action=deploy -b --vault-password-file ~/.vault-pass

test-upgrade:
	@echo "⬆️  Upgrading test cluster..."
	ansible-playbook -i inventory-test.ini playbooks/upgrade-cluster.yaml -b --vault-password-file ~/.vault-pass

test-health:
	@echo "🏥 Checking test cluster health..."
	ansible-playbook -i inventory-test.ini playbooks/etcd-health.yaml

test-backup:
	@echo "💾 Creating test cluster backup..."
	ansible-playbook -i inventory-test.ini playbooks/etcd-cluster.yaml -e etcd_action=backup -b --vault-password-file ~/.vault-pass

test-restore:
	@echo "♻️  Restoring test cluster from backup..."
	ansible-playbook -i inventory-test.ini playbooks/restore-etcd-cluster.yaml -e restore_confirm=false -b --vault-password-file ~/.vault-pass

test-delete:
	@echo "🗑️  Deleting test cluster..."
	ansible-playbook -i inventory-test.ini playbooks/etcd-cluster.yaml -e etcd_delete_cluster=true -b --vault-password-file ~/.vault-pass

test-clean: test-delete
	@echo "✅ Test cluster cleaned up"

# Documentation targets
docs-serve:
	@echo "Starting documentation server..."
	mkdocs serve

docs-build:
	@echo "Building documentation..."
	mkdocs build

docs-deploy:
	@echo "Deploying documentation to GitHub Pages..."
	mkdocs gh-deploy --force

docs-clean:
	@echo "Cleaning documentation build..."
	rm -rf site/

docs: docs-serve

help:
	@echo "Production targets:"
	@echo "  make create-cluster  - Create production etcd cluster"
	@echo "  make upgrade-cluster - Upgrade production etcd cluster"
	@echo "  make delete-cluster  - Delete production etcd cluster"
	@echo "  make clean           - Clean temporary files"
	@echo ""
	@echo "🧪 TEST ENVIRONMENT (uses inventory-test.ini)"
	@echo "  make test                - Quick test (create + health check)"
	@echo "  make test-all            - Full test suite (create/backup/upgrade/restore/delete)"
	@echo "  make test-create         - Create test cluster"
	@echo "  make test-deploy         - Deploy/update test cluster"
	@echo "  make test-upgrade        - Upgrade test cluster"
	@echo "  make test-health         - Health check test cluster"
	@echo "  make test-backup         - Backup test cluster"
	@echo "  make test-restore        - Restore test cluster"
	@echo "  make test-delete         - Delete test cluster"
	@echo "  make test-clean          - Alias for test-delete"
	@echo ""
	@echo "📚 DOCUMENTATION"
	@echo "  make docs                - Serve docs locally at http://127.0.0.1:8000"
	@echo "  make docs-build          - Build static site"
	@echo "  make docs-deploy         - Deploy to GitHub Pages"
	@echo ""
	@echo "🧹 MAINTENANCE"
	@echo "  make clean               - Clean temporary files"
	@echo ""
	@echo "════════════════════════════════════════════════════════════════════════════════"
	@echo "💡 QUICK START:"
	@echo "   Production:"
	@echo "     1. cp inventory-example.ini inventory.ini"
	@echo "     2. Edit inventory.ini with your nodes"
	@echo "     3. cp group_vars/all/vault.yml.example group_vars/all/vault.yml"
	@echo "     4. Edit vault.yml and encrypt: ansible-vault encrypt group_vars/all/vault.yml"
	@echo "     5. make create-cluster"
	@echo ""
	@echo "   Testing:"
	@echo "     1. cp inventory-example.ini inventory-test.ini"
	@echo "     2. Edit inventory-test.ini with your test nodes"
	@echo "     3. make test"
	@echo ""
	@echo "📖 Full documentation: make docs"
	@echo "════════════════════════════════════════════════════════════════════════════════"
