# Health Checks

Monitor the health and performance of your etcd cluster.

## Basic Health Checks

### Cluster Health

```bash
etcdctl endpoint health --cluster
```

### Member Status

```bash
etcdctl endpoint status --write-out=table
```

### Alarm Status

```bash
etcdctl alarm list
```

## Performance Checks

### Check Latency

```bash
etcdctl check perf
```

### Benchmark

```bash
benchmark --endpoints=https://10.0.1.10:2379 \
  --cert=/etc/etcd/ssl/etcd-k8s-1-client.crt \
  --key=/etc/etcd/ssl/etcd-k8s-1-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  put --total=10000 --key-size=8 --val-size=256
```

## Backup Monitoring

### Deadman Switch (Heartbeat)

The automated backup scripts support a "deadman switch" monitoring URL (e.g., Healthchecks.io, Dead Man's Snitch). If the backup fails to run or complete, the monitoring service will alert you.

**Configuration:**

```yaml
# In group_vars/all/vars.yml
backup_healthcheck_enabled: true
backup_healthcheck_url: "https://hc-ping.com/your-uuid-for-etcd-data"
ca_backup_healthcheck_url: "https://hc-ping.com/your-uuid-for-ca"
```

## Certificate Health

### Check Expiration

```bash
# Check certificate expiration
step certificate inspect /etc/etcd/ssl/etcd-k8s-1-peer.crt

# Check renewal timers
systemctl list-timers 'step-renew-*'
```

## Related Documentation

- [Cluster Management](cluster-management.md)
- [Certificate Renewal](../certificates/renewal.md)
