# Upgrade Cluster

Upgrade etcd to a new version with zero downtime.

## Upgrade Process

### 1. Backup Before Upgrade

```bash
ansible-playbook -i inventory.ini etcd.yaml \
  -e etcd_action=backup \
  --vault-password-file ~/.vault-pass -b
```

### 2. Run Upgrade

```bash
ansible-playbook -i inventory.ini etcd.yaml \
  -e etcd_action=upgrade \
  -e etcd_version=v3.5.26 \
  --vault-password-file ~/.vault-pass -b
```

### 3. Verify Cluster Health

```bash
sudo etcdctl endpoint health
```

## Upgrade Safety

- Automatic backup before upgrade
- Health check before proceeding
- One node at a time (rolling restart)
- Verifies health after each node

## Related Documentation

- [Cluster Management](cluster-management.md)
- [Backup & Restore](backup-restore.md)
