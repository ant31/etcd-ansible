# Multi-Cluster Setup

Deploy and manage multiple independent etcd clusters.

## Use Cases

- Separate clusters for different applications
- Kubernetes main cluster + events cluster
- Environment separation (dev/staging/prod)

## Configuration

### Separate Inventories

```bash
# Deploy main cluster
ansible-playbook -i inventory-main.ini etcd.yaml \
  -e etcd_action=create \
  -e etcd_cluster_name=main

# Deploy events cluster
ansible-playbook -i inventory-events.ini etcd.yaml \
  -e etcd_action=create \
  -e etcd_cluster_name=events
```

### Single Inventory with Groups

```ini
[etcd-main]
etcd-main-1 ansible_host=10.0.1.10

[etcd-events]
etcd-events-1 ansible_host=10.0.2.10

[etcd:children]
etcd-main
etcd-events
```

## Related Documentation

- [Cluster Management](../operations/cluster-management.md)
