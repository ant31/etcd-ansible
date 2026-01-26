# High Availability Setup

Configure high availability for etcd and certificate management.

## Multi-Node etcd Cluster

Deploy at least 3 nodes (odd number):

```ini
[etcd]
etcd-1 ansible_host=10.0.1.10
etcd-2 ansible_host=10.0.1.11
etcd-3 ansible_host=10.0.1.12
etcd-4 ansible_host=10.0.1.13
etcd-5 ansible_host=10.0.1.14
```

**Fault Tolerance:**
- 3 nodes: 1 failure
- 5 nodes: 2 failures
- 7 nodes: 3 failures

## Multiple Cert-Managers

Configure backup cert-managers for CA redundancy:

```ini
[etcd-cert-managers]
etcd-1  # Primary - step-ca running
etcd-2  # Backup - CA keys replicated
etcd-3  # Backup - CA keys replicated
```

Deploy with CA replication:

```bash
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create
ansible-playbook -i inventory.ini playbooks/replicate-ca.yaml
```

## Manual Failover

If primary cert-manager fails:

```bash
# Activate step-ca on backup
ssh etcd-2
sudo systemctl start step-ca

# Verify
curl -k https://localhost:9000/health
```

## Related Documentation

- [Cluster Management](../operations/cluster-management.md)
- [Certificate Disaster Recovery](../certificates/disaster-recovery.md)
