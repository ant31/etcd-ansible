# Performance Tuning

Optimize etcd cluster performance for your workload.

## Hardware Recommendations

### CPU
- Development: 2 cores
- Production: 4-8 cores

### Memory
- Development: 2 GB
- Production: 8-16 GB

### Disk
- **SSD Required** for production
- 50+ GB for data
- Test with: `fio --name=test --ioengine=libaio --rw=randwrite --bs=4k`

## Configuration Tuning

### Heartbeat and Election

```yaml
# In group_vars/all/etcd.yml
etcd_heartbeat_interval: 250  # Default: 250ms
etcd_election_timeout: 5000    # Default: 5000ms
```

### Snapshot Settings

```yaml
etcd_snapshot_count: 10000  # Snapshot after 10k operations
etcd_max_snapshots: 5       # Keep last 5 snapshots
etcd_max_wals: 5            # Keep last 5 WAL files
```

### Compaction

```yaml
etcd_compaction_retention: "8"  # Keep last 8 hours of history
```

## Monitoring Performance

```bash
# Check performance
etcdctl check perf

# Benchmark writes
benchmark --endpoints=https://10.0.1.10:2379 put --total=10000
```

## Related Documentation

- [Cluster Management](../operations/cluster-management.md)
- [Health Checks](../operations/health-checks.md)
