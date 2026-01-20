# Available Playbooks

Overview of all available playbooks for etcd cluster management.

## Main Playbooks

### `etcd.yaml`

Main cluster deployment playbook.

```bash
# Create new cluster
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create

# Upgrade cluster
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=upgrade

# Backup cluster
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=backup

# Delete cluster
ansible-playbook -i inventory.ini etcd.yaml -e etcd_delete_cluster=true
```

## Backup Playbooks

### `playbooks/backup-ca.yaml`

Backup CA keys to encrypted S3 storage.

```bash
ansible-playbook -i inventory.ini playbooks/backup-ca.yaml \
  --vault-password-file ~/.vault-pass
```

## Restore Playbooks

### `playbooks/restore-ca-from-backup.yaml`

Restore CA keys from S3 backup.

```bash
ansible-playbook -i inventory.ini playbooks/restore-ca-from-backup.yaml \
  -e target_node=etcd-k8s-1 \
  --vault-password-file ~/.vault-pass
```

### `playbooks/restore-ca.yaml`

Restore CA keys from another cert-manager node.

```bash
ansible-playbook -i inventory.ini playbooks/restore-ca.yaml \
  -e source_node=etcd-k8s-2 \
  -e target_node=etcd-k8s-1
```

### `playbooks/restore-etcd-cluster.yaml`

Restore etcd data from backup.

```bash
ansible-playbook -i inventory.ini playbooks/restore-etcd-cluster.yaml
```

## Utility Playbooks

### `playbooks/replicate-ca.yaml`

Replicate CA keys to backup cert-managers.

```bash
ansible-playbook -i inventory.ini playbooks/replicate-ca.yaml
```

### `playbooks/setup-kms.yaml`

Setup AWS KMS key for backup encryption.

```bash
ansible-playbook playbooks/setup-kms.yaml
```

## Related Documentation

- [Creating Custom Playbooks](custom.md)
- [Integration Examples](integration.md)
