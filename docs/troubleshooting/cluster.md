# Cluster Issues

Troubleshooting etcd cluster problems.

## Cluster Won't Form

**Symptom:**
```
waiting for initial cluster to be healthy
```

**Solution:**
```bash
# Check network connectivity between nodes
ping etcd-k8s-2
ping etcd-k8s-3

# Check peer ports
telnet etcd-k8s-2 2380

# Verify cluster configuration
cat /etc/etcd/etcd-default-1-conf.yaml | grep initial-cluster
```

## Member Won't Join

**Symptom:**
```
member already exists in cluster
```

**Solution:**
```bash
# List members
etcdctl member list

# Remove old member
etcdctl member remove <MEMBER_ID>

# Re-add member
etcdctl member add etcd-k8s-2 --peer-urls=https://10.0.1.11:2380
```

## Database Size Too Large

**Symptom:**
```
mvcc: database space exceeded
```

**Solution:**
```bash
# Compact database
rev=$(etcdctl endpoint status --write-out="json" | jq -r '.[0].Status.header.revision')
etcdctl compact $rev

# Defragment
etcdctl defrag

# Disarm alarm
etcdctl alarm disarm
```

## Related Documentation

- [Common Issues](common-issues.md)
- [Debug Commands](debug-commands.md)
