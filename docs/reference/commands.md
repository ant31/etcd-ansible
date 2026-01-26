# Commands Reference

Quick reference for common etcdctl commands.

## Cluster Commands

```bash
# Check health
etcdctl endpoint health

# List members
etcdctl member list

# Get status
etcdctl endpoint status --write-out=table
```

## Data Commands

```bash
# Put key
etcdctl put /key value

# Get key
etcdctl get /key

# Delete key
etcdctl del /key

# List keys with prefix
etcdctl get --prefix /path/
```

## Maintenance Commands

```bash
# Compact database
etcdctl compact <revision>

# Defragment
etcdctl defrag

# Snapshot
etcdctl snapshot save snapshot.db
```

## Related Documentation

- [Variables Reference](variables.md)
- [Architecture](architecture.md)
