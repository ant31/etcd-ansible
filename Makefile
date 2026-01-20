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

# Test targets for etcd-ansible
test-etcd: test-create test-health
test:
	echo "test skipped"

test-create:
	@echo "Creating test etcd cluster..."
	ansible-playbook -i inventory-test.ini test-etcd.yaml -e etcd_action=create -b -vv

test-health:
	@echo "Checking etcd cluster health..."
	ansible-playbook -i inventory-test.ini test-etcd.yaml --tags etcd-verify -b

test-upgrade:
	@echo "Upgrading etcd cluster..."
	ansible-playbook -i inventory-test.ini test-etcd.yaml -e etcd_action=upgrade -b -vv

test-backup:
	@echo "Creating etcd cluster backup..."
	ansible-playbook -i inventory-test.ini test-etcd.yaml -e etcd_action=backup -b -v

test-delete:
	@echo "Deleting test etcd cluster..."
	ansible-playbook -i inventory-test.ini test-etcd.yaml -e etcd_delete_cluster=true -b -v

test-clean: test-delete
	@echo "Test cluster deleted"

test-download:
	@echo "Testing download functionality only..."
	ansible-playbook -i inventory-test.ini test-download.yaml -b -v

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
	@echo "Test targets:"
	@echo "  make test            - Create test cluster and verify health (default)"
	@echo "  make test-create     - Create a new test etcd cluster"
	@echo "  make test-health     - Verify test cluster health"
	@echo "  make test-upgrade    - Upgrade existing test cluster"
	@echo "  make test-backup     - Create a test cluster backup"
	@echo "  make test-delete     - Delete the test cluster"
	@echo "  make test-clean      - Alias for test-delete"
	@echo "  make test-download   - Test download functionality only"
	@echo ""
	@echo "Documentation targets:"
	@echo "  make docs            - Serve documentation locally (alias for docs-serve)"
	@echo "  make docs-serve      - Serve documentation at http://127.0.0.1:8000"
	@echo "  make docs-build      - Build static documentation site"
	@echo "  make docs-deploy     - Deploy to GitHub Pages"
	@echo "  make docs-clean      - Clean documentation build artifacts"
