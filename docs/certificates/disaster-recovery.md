# Certificate Disaster Recovery

Recovery procedures for certificate-related failures.

## Scenarios

### Scenario 1: Primary Cert-Manager Fails

**RTO:** 5-10 minutes

**Steps:**

1. Activate step-ca on backup node:
```bash
ssh etcd-k8s-2
sudo systemctl start step-ca
```

2. Verify health:
```bash
curl -k https://10.0.1.11:9000/health
```

### Scenario 2: CA Keys Lost

**RTO:** 10-30 minutes

**Steps:**

1. Restore from backup:
```bash
ansible-playbook -i inventory.ini playbooks/restore-ca-from-backup.yaml \
  -e target_node=etcd-k8s-1 \
  --vault-password-file ~/.vault-pass
```

2. Verify step-ca:
```bash
sudo systemctl status step-ca
curl -k https://localhost:9000/health
```

### Scenario 3: Certificate Expired

**RTO:** 5 minutes

**Steps:**

1. Force certificate renewal:
```bash
sudo systemctl start step-renew-etcd-k8s-1-peer.service
sudo systemctl start step-renew-etcd-k8s-1-server.service
sudo systemctl start step-renew-etcd-k8s-1-client.service
```

2. Reload etcd:
```bash
sudo systemctl reload etcd-default-1
```

## Related Documentation

- [Certificate Overview](overview.md)
- [Certificate Renewal](renewal.md)
- [Backup & Restore](../operations/backup-restore.md)
