# Etcd-Ansible Playbooks

This directory contains all operational playbooks for managing etcd clusters.

## Core Playbooks

### Cluster Management

| Playbook | Purpose | Usage |
|----------|---------|-------|
| `etcd-cluster.yaml` | Main cluster lifecycle management | `ansible-playbook -i inventory.ini playbooks/etcd-cluster.yaml -e etcd_action=create -b` |
| `upgrade-cluster.yaml` | Safe rolling upgrade | `ansible-playbook -i inventory.ini playbooks/upgrade-cluster.yaml -e etcd_version=v3.5.26 -b` |
| `etcd-health.yaml` | Comprehensive health checks | `ansible-playbook -i inventory.ini playbooks/etcd-health.yaml` |

### Backup & Restore

| Playbook | Purpose | Usage |
|----------|---------|-------|
| `backup-ca.yaml` | Backup CA keys to S3 | `ansible-playbook -i inventory.ini playbooks/backup-ca.yaml --vault-password-file ~/.vault-pass` |
| `restore-ca.yaml` | Restore CA from another node | `ansible-playbook -i inventory.ini playbooks/restore-ca.yaml -e source_node=etcd-2 -e target_node=etcd-1` |
| `restore-ca-from-backup.yaml` | Restore CA from S3 backup | `ansible-playbook -i inventory.ini playbooks/restore-ca-from-backup.yaml -e target_node=etcd-1` |
| `restore-etcd-cluster.yaml` | Restore cluster data | `ansible-playbook -i inventory.ini playbooks/restore-etcd-cluster.yaml` |

### Certificate Management

| Playbook | Purpose | Usage |
|----------|---------|-------|
| `replicate-ca.yaml` | Replicate CA to backup nodes | `ansible-playbook -i inventory.ini playbooks/replicate-ca.yaml` |
| `setup-kms.yaml` | Setup AWS KMS for encryption | `ansible-playbook playbooks/setup-kms.yaml -e kms_key_alias=alias/etcd-ca-backup` |

### Advanced

| Playbook | Purpose | Usage |
|----------|---------|-------|
| `multi-cluster-example.yaml` | Deploy multiple clusters | `ansible-playbook -i inventory-multi-cluster-example.ini playbooks/multi-cluster-example.yaml -b` |

## Quick Reference

### Production Operations

```bash
# Create cluster
make create-cluster
# or: ansible-playbook -i inventory.ini playbooks/etcd-cluster.yaml -e etcd_action=create -b

# Upgrade cluster
make upgrade-cluster
# or: ansible-playbook -i inventory.ini playbooks/upgrade-cluster.yaml -e etcd_version=v3.5.26 -b

# Health check
make health-check
# or: ansible-playbook -i inventory.ini playbooks/etcd-health.yaml

# Backup
make backup-cluster    # etcd data
make backup-ca         # CA keys

# Restore
make restore-cluster   # etcd data
make restore-ca        # CA keys

# Delete
make delete-cluster    # requires confirmation
```

### Test Environment

Test environment uses the SAME playbooks as production, just with inventory-test.ini:

```bash
# Create test cluster
make test-create
# or: ansible-playbook -i inventory-test.ini playbooks/etcd-cluster.yaml -e etcd_action=create -b

# Run all tests (create → backup → upgrade → restore → delete)
make test-all

# Individual test operations
make test-health       # Health check
make test-backup       # Create backup
make test-upgrade      # Upgrade version
make test-restore      # Restore from backup
make test-delete       # Clean up
```

## Multi-Cluster Example

See `multi-cluster-example.yaml` and `../inventory-multi-cluster-example.ini` for running two independent etcd clusters:

- **k8s** cluster: ports 2379/2380
- **k8s-events** cluster: ports 2381/2382

Both running on the same nodes with separate:
- Data directories
- Certificates
- Systemd services
- Backup schedules

```bash
ansible-playbook -i inventory-multi-cluster-example.ini playbooks/multi-cluster-example.yaml -e etcd_action=create -b
```

## Common Patterns

### Target Specific Cluster (Multi-Cluster)
```bash
# Health check only k8s cluster
ansible-playbook -i inventory.ini playbooks/etcd-health.yaml --limit=etcd-k8s

# Upgrade only events cluster
ansible-playbook -i inventory.ini playbooks/upgrade-cluster.yaml --limit=etcd-k8s-events
```

### Skip Confirmation Prompts
```bash
# Restore without confirmation
ansible-playbook -i inventory.ini playbooks/restore-etcd-cluster.yaml -e restore_confirm=false
```

### Force Operations (Use with Caution)
```bash
# Force upgrade on unhealthy cluster (DANGEROUS)
ansible-playbook -i inventory.ini playbooks/upgrade-cluster.yaml -e etcd_force_deploy=true

# Force create (destroys existing data)
ansible-playbook -i inventory.ini playbooks/etcd-cluster.yaml -e etcd_action=create -e etcd_force_create=true
```

## See Also

- [Main README](../README.md)
- [Certificate Architecture](../CERTIFICATE_ARCHITECTURE.md)
- [Makefile](../Makefile) - Common operations
- [Documentation](../docs/)
