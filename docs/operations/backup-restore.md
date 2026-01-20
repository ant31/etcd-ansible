# Backup & Restore

Comprehensive backup and restore procedures for etcd clusters.

## Automated Backups

Automated backups are configured during cluster deployment.

### CA Backups (Change-based)

- Checks every 5 minutes if CA files changed
- Only backs up when changes detected
- Encrypted with AWS KMS
- Uploaded to S3

### Etcd Data Backups (Time-based)

- Runs every 30 minutes (configurable)
- Creates snapshot of cluster data
- Encrypted with AWS KMS
- Uploaded to S3
- Retention: 90 days (configurable)

### View Backup Logs

```bash
# CA backup logs
sudo tail -f /var/log/etcd-backups/ca-backup.log

# Etcd data backup logs
sudo tail -f /var/log/etcd-backups/etcd-backup.log
```

## Manual Backup

### Backup CA Keys

```bash
ansible-playbook -i inventory.ini playbooks/backup-ca.yaml \
  --vault-password-file ~/.vault-pass
```

### Backup etcd Data

```bash
ansible-playbook -i inventory.ini etcd.yaml \
  -e etcd_action=backup \
  --vault-password-file ~/.vault-pass -b
```

## Restore Procedures

### Restore CA Keys

```bash
# From S3 backup
ansible-playbook -i inventory.ini playbooks/restore-ca-from-backup.yaml \
  -e target_node=etcd-k8s-1 \
  --vault-password-file ~/.vault-pass

# From another cert-manager node
ansible-playbook -i inventory.ini playbooks/restore-ca.yaml \
  -e source_node=etcd-k8s-2 \
  -e target_node=etcd-k8s-1
```

### Restore etcd Data

```bash
# From latest S3 backup
ansible-playbook -i inventory.ini playbooks/restore-etcd-cluster.yaml

# From specific backup
ansible-playbook -i inventory.ini playbooks/restore-etcd-cluster.yaml \
  -e restore_etcd_s3_file="etcd-default/2026/01/snapshot.db.kms"

# From local file
ansible-playbook -i inventory.ini playbooks/restore-etcd-cluster.yaml \
  -e restore_etcd_local_file="/path/to/snapshot.db"
```

## Related Documentation

- [Cluster Management](cluster-management.md)
- [Certificate Disaster Recovery](../certificates/disaster-recovery.md)
