# Frequently Asked Questions

## General Questions

### What is etcd-ansible?

etcd-ansible is an Ansible automation for deploying production-grade etcd clusters with automated certificate management using Smallstep CA.

### Do I need Kubernetes?

No, etcd-ansible works with or without Kubernetes. It can be used for any etcd deployment.

### What operating systems are supported?

Ubuntu 20.04+, Debian 11+, RHEL 8+, CentOS 8+, Rocky Linux 8+, and CoreOS.

## Certificate Questions

### How long do certificates last?

Default: 2 years (17520 hours). Configurable via `step_cert_default_duration`.

### When do certificates renew?

Automatically at 2/3 of their lifetime (~487 days for 2-year certificates).

### Do private keys leave the node?

No, private keys are generated locally and never transmitted over the network.

### What if cert-manager fails?

Activate step-ca on a backup cert-manager node. See [HA Setup](../advanced/ha-setup.md).

## Backup Questions

### Where are backups stored?

- Local: `/var/lib/etcd/backups/`
- S3: Configured bucket with KMS encryption

### How often are backups created?

- CA backups: When changes detected (every 5 minutes check)
- etcd data: Every 30 minutes (configurable)

### How do I restore from backup?

Use the restore playbooks:
```bash
ansible-playbook -i inventory.ini playbooks/restore-etcd-cluster.yaml
```

## Cluster Questions

### Can I add nodes later?

Yes, add to inventory and run the playbook with `--limit=new-node`.

### Can I upgrade etcd version?

Yes, use `etcd_action=upgrade` with new `etcd_version`.

### What about multi-cluster?

Each cluster is independent. Deploy with different `etcd_cluster_name`.

## Troubleshooting Questions

### etcd won't start

Check logs: `journalctl -u etcd-default-1 -n 100`

See [Common Issues](../troubleshooting/common-issues.md).

### Certificates expired

Renew manually: `systemctl start step-renew-etcd-k8s-1-peer.service`

### Cluster unhealthy

Check each node: `etcdctl endpoint health`

See [Cluster Issues](../troubleshooting/cluster.md).

## Related Documentation

- [Getting Started](../getting-started/introduction.md)
- [Operations Guide](../operations/cluster-management.md)
- [Troubleshooting](../troubleshooting/common-issues.md)
