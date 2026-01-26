# Creating Custom Playbooks

Guide to creating custom playbooks for your etcd clusters.

## Basic Playbook Structure

```yaml
---
- name: My custom etcd operation
  hosts: etcd
  gather_facts: yes
  roles:
    - role: etcd3
    - role: etcd3/facts
  
  tasks:
    - name: My custom task
      debug:
        msg: "etcd endpoint: {{ etcd_client_url }}"
```

## Using etcd3/facts Role

The `etcd3/facts` role provides cluster information:

```yaml
- hosts: kube-master
  roles:
    - etcd3/facts
  
  tasks:
    - name: Display etcd endpoints
      debug:
        msg: "{{ etcd_access_addresses }}"
```

Available facts:
- `etcd_access_addresses` - Comma-separated endpoints
- `etcd_peer_addresses` - Peer URLs
- `etcd_cert_paths` - Certificate file paths
- `etcd_members` - Dict of all cluster members

## Related Documentation

- [Available Playbooks](overview.md)
- [Integration Examples](integration.md)
