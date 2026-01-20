# Cluster Management

Day-2 operations for managing your etcd clusters.

## Common Operations

### Check Cluster Status

```bash
# Check cluster health
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379,https://etcd-k8s-2:2379,https://etcd-k8s-3:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint health
```

### View Cluster Members

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  member list
```

### Check Database Size

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint status --write-out=table
```

## Service Management

### Restart etcd Service

```bash
# On specific node
sudo systemctl restart etcd-default-1

# Using Ansible (all nodes)
ansible etcd -i inventory.ini -m systemd -a "name=etcd-default-1 state=restarted" -b
```

### View Logs

```bash
# Recent logs
sudo journalctl -u etcd-default-1 -n 100

# Follow logs
sudo journalctl -u etcd-default-1 -f

# Logs from specific time
sudo journalctl -u etcd-default-1 --since "2026-01-20 10:00:00"
```

## Data Operations

### Compact etcd Database

```bash
# Get current revision
rev=$(sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint status --write-out="json" | jq -r '.[0].Status.header.revision')

# Compact
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  compact $rev
```

### Defragment Database

```bash
# Defragment all endpoints
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379,https://etcd-k8s-2:2379,https://etcd-k8s-3:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  defrag
```

## Monitoring

### Check Alarm Status

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  alarm list
```

### Performance Check

```bash
sudo etcdctl \
  --endpoints=https://etcd-k8s-1:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  check perf
```

## Related Documentation

- [Backup & Restore](backup-restore.md)
- [Upgrade Cluster](upgrade.md)
- [Scaling](scaling.md)
- [Health Checks](health-checks.md)
