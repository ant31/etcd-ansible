# etcd-ansible
Deploy and manage etcd cluster via Ansible

## Certs management
The certificate are generate from the `etcd-cert-managers` hosts then each nodes, etcd clients and peers, downloads its own certificate tarball.

##### Playbook example 
To only manage certificate (without deploying an etcd cluster), the following playbook initializes the CA and sends certificates to the hosts 
```
- hosts: etcd-cert-managers
  roles:
    # Create the CA certs
    - name: etcd/certs/ca
- hosts: etcd-all
  roles:
    - name: etcd/certs/fetch
```

Also, `/etcd/certs/fetch` can be set as a role dependency. Actually, this how the etcd-peer certificate are generated: [roles/etcd/cluster/meta/main.yml](https://github.com/ant31/etcd-ansible/blob/master/roles/etcd/cluster/meta/main.yml#L13)

Roles documentation can be found here: [/etcd/certs/README.md)](https://github.com/ant31/etcd-ansible/tree/master/roles/etcd/certs/README.md)


