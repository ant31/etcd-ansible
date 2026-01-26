# Integration Examples

Examples of integrating etcd with other systems.

## Kubernetes Integration

```yaml
- hosts: kube-master
  roles:
    - etcd3/facts
  
  tasks:
    - name: Configure kube-apiserver
      template:
        src: kube-apiserver.yaml.j2
        dest: /etc/kubernetes/manifests/kube-apiserver.yaml
```

Template example:

```yaml
# kube-apiserver.yaml.j2
spec:
  containers:
  - name: kube-apiserver
    command:
    - kube-apiserver
    - --etcd-servers={{ etcd_access_addresses }}
    - --etcd-cafile={{ etcd_cert_paths.client.ca }}
    - --etcd-certfile={{ etcd_cert_paths.client.cert }}
    - --etcd-keyfile={{ etcd_cert_paths.client.key }}
```

## Application Integration

```yaml
- hosts: app-servers
  roles:
    - etcd3/facts
  
  tasks:
    - name: Configure application
      template:
        src: app-config.yaml.j2
        dest: /etc/myapp/config.yaml
```

## Related Documentation

- [Available Playbooks](overview.md)
- [Creating Custom Playbooks](custom.md)
