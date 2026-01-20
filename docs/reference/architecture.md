# Ansible Architecture

How this Ansible repository is structured and how the roles interact.

## Role Dependency Graph

```
etcd.yaml (main playbook)
  └── imports role: etcd3/cluster
       └── meta/main.yml triggers:
            └── etcd3/cluster/install
                 └── meta/main.yml dependencies:
                      ├── etcd3 (base)
                      ├── adduser (creates etcd user)
                      ├── etcd3/facts (generates variables)
                      ├── etcd3/certs/smallstep (CA + certs)
                      ├── etcd3/download (binaries)
                      └── etcd3/backups/cron (automated backups)
```

## How Roles Execute

### 1. `roles/etcd3/cluster/tasks/main.yaml`

This is the orchestration role that decides what to do:

```yaml
# Checks etcd_action variable and imports appropriate role:
- import_role: etcd3/backups      # If etcd_action=backup
- import_role: etcd3/cluster/install  # If etcd_action=create|upgrade
- import_role: etcd3/cluster/delete   # If etcd_delete_cluster=true
```

### 2. `roles/etcd3/cluster/install/`

Deploys the cluster via `meta/main.yml` dependencies:

```yaml
dependencies:
  - name: etcd3/certs/smallstep   # ← RUNS BEFORE etcd install
  - name: etcd3/download
  - name: etcd3/backups/cron
```

Then runs `tasks/main.yml`:
- Copies etcd binaries from download dir
- Generates etcd configuration (`etcd-conf.yaml.j2`)
- Creates systemd service (`etcd-host.service.j2`)
- Starts etcd cluster

### 3. `roles/etcd3/certs/smallstep/tasks/main.yml`

Routes to different tasks based on node type:

```yaml
- include_tasks: install-ca.yml
  when: inventory_hostname in groups[etcd_certmanagers_group]
  # Runs ONLY on nodes in [etcd-cert-managers]
  # Installs step-ca, initializes CA, replicates to backups

- include_tasks: install-client.yml
  # Runs on ALL nodes
  # Installs step CLI, requests certificates

- include_tasks: configure-renewal.yml
  # Runs on ALL nodes
  # Creates systemd renewal timers
```

### 4. `roles/etcd3/facts/tasks/main.yaml`

Generates cluster topology variables:

```yaml
# Loops through groups[etcd_cluster_group] and creates:
etcd_members:
  etcd-k8s-1:
    etcd_name: "etcd-default-1"
    etcd_peer_url: "https://10.0.1.10:2380"
    etcd_client_url: "https://10.0.1.10:2379"
  etcd-k8s-2: ...
  
# Also creates:
etcd_access_addresses: "https://10.0.1.10:2379,https://10.0.1.11:2379,..."
etcd_peer_addresses: "etcd-default-1=https://10.0.1.10:2380,..."
```

These variables are used in templates.

## Template System

### Configuration Templates

**`roles/etcd3/cluster/install/templates/etcd-conf.yaml.j2`:**
```jinja2
name: {{etcd_name}}
data-dir: {{etcd_data_dir}}
listen-peer-urls: https://{{etcd_address}}:{{etcd_ports['peer']}}
listen-client-urls: https://{{etcd_address}}:{{etcd_ports['client']}}
initial-cluster: {{etcd_peer_addresses}}   # ← From etcd3/facts
client-transport-security:
  cert-file: {{etcd_cert_paths.server.cert}}  # ← From defaults
  key-file: {{etcd_cert_paths.server.key}}
```

**`roles/etcd3/backups/cron/templates/etcd-backup.sh.j2`:**
```bash
ETCD_ENDPOINTS="{{ etcd_access_addresses }}"  # ← From etcd3/facts
CERT="{{ etcd_cert_paths.client.cert }}"      # ← From defaults
```

## Variable Precedence

1. **Role defaults** - `roles/etcd3/defaults/main.yaml`
2. **Group vars** - `group_vars/all/*.yml`
3. **Inventory vars** - In `inventory.ini` with `[group:vars]`
4. **Extra vars** - `-e var=value` on command line (highest priority)

## Task Execution Flow

For `ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create`:

```
1. Parse inventory.ini
   └── Identify groups: [etcd], [etcd-cert-managers], [etcd-clients]

2. Load variables
   ├── roles/etcd3/defaults/main.yaml
   ├── roles/etcd3/certs/smallstep/defaults/main.yml
   └── group_vars/all/vault.yml (decrypted)

3. Execute on hosts: etcd group
   
4. Run role: etcd3/cluster
   └── Checks etcd_action=create
       └── Imports: etcd3/cluster/install
   
5. Role dependencies execute (via meta/main.yml):
   a. etcd3/facts
      └── Generates etcd_members, etcd_access_addresses
   
   b. etcd3/certs/smallstep
      └── On [etcd-cert-managers][0]: install-ca.yml
          ├── Install step-ca binary
          ├── Run: step ca init
          ├── Start step-ca service
          └── Replicate CA keys to backup cert-managers
      └── On all [etcd]: install-client.yml
          ├── Install step CLI
          ├── Request certificates from step-ca
          └── configure-renewal.yml
              └── Create systemd timers for auto-renewal
   
   c. etcd3/download
      └── Download etcd/etcdctl/etcdutl binaries
   
   d. etcd3/backups/cron
      └── Setup automated backup cron jobs

6. etcd3/cluster/install/tasks/main.yml
   ├── Copy binaries from download dir to /opt/bin
   ├── Template: etcd-conf.yaml.j2 → /etc/etcd/etcd-default-1-conf.yaml
   ├── Template: etcd-host.service.j2 → /etc/systemd/system/etcd-default-1.service
   ├── systemctl daemon-reload
   └── systemctl start etcd-default-1

7. Verify cluster health
```

## Important Files Generated by This Repository

### On Cert-Manager Nodes (from `[etcd-cert-managers]`)

**Created by `roles/etcd3/certs/smallstep/tasks/install-ca.yml`:**
```
/etc/step-ca/
├── config/ca.json                    # step-ca configuration
├── certs/root_ca.crt                 # Root CA certificate
├── secrets/root_ca_key               # Root CA private key (0400)
├── certs/intermediate_ca.crt         # Intermediate CA cert
├── secrets/intermediate_ca_key       # Intermediate CA key (0400)
├── secrets/password                  # CA password (0400)
└── db/                               # Certificate database

/opt/bin/
├── step-ca                           # step-ca binary
└── step                              # step CLI binary

/etc/systemd/system/
└── step-ca.service                   # step-ca systemd service
```

### On All etcd Nodes (from `[etcd]`)

**Created by `roles/etcd3/cluster/install/`:**
```
/var/lib/etcd/etcd-default-1/         # etcd data directory
/etc/etcd/
├── etcd-default-1-conf.yaml          # etcd configuration (from template)
├── etcd-default-1.env                # Environment variables
└── ssl/                              # Certificates (from smallstep role)
    ├── etcd-default-1-peer.crt
    ├── etcd-default-1-peer.key       # (0400)
    ├── etcd-default-1-server.crt
    ├── etcd-default-1-server.key     # (0400)
    ├── etcd-default-1-client.crt
    ├── etcd-default-1-client.key     # (0400)
    └── root_ca.crt

/opt/bin/
├── etcd                              # etcd binary
├── etcdctl                           # etcd client
├── etcdutl                           # etcd utility
└── step                              # step CLI

/etc/systemd/system/
├── etcd-default-1.service            # etcd systemd service
├── step-renew-etcd-default-1-peer.service
├── step-renew-etcd-default-1-peer.timer
├── step-renew-etcd-default-1-server.service
├── step-renew-etcd-default-1-server.timer
├── step-renew-etcd-default-1-client.service
└── step-renew-etcd-default-1-client.timer
```

**Created by `roles/etcd3/backups/cron/`:**
```
/opt/etcd-backup-scripts/
├── ca-backup-check.sh                # From template
└── etcd-backup.sh                    # From template

/var/log/etcd-backups/
├── ca-backup.log
└── etcd-backup.log

/etc/logrotate.d/
├── etcd-ca-backup
└── etcd-backup

Crontab entries (root):
*/5 * * * * /opt/etcd-backup-scripts/ca-backup-check.sh >> /var/log/etcd-backups/ca-backup.log 2>&1
*/30 * * * * /opt/etcd-backup-scripts/etcd-backup.sh >> /var/log/etcd-backups/etcd-backup.log 2>&1
```

## How Inventory Groups Map to Roles

| Inventory Group | Variable Name | Used By Roles |
|----------------|---------------|---------------|
| `[etcd]` | `groups['etcd']` | `etcd3/cluster/install`, `etcd3/facts`, `etcd3/certs/smallstep` |
| `[etcd-cert-managers]` | `groups['etcd-cert-managers']` | `etcd3/certs/smallstep/tasks/install-ca.yml` |
| `[etcd-clients]` | `groups['etcd-clients']` | `etcd3/certs/smallstep/tasks/install-client.yml` |

Accessed via:
```yaml
# Get first etcd node
groups[etcd_cluster_group][0]

# Check if current node is cert-manager
inventory_hostname in groups[etcd_certmanagers_group]

# Loop through all etcd nodes
loop: "{{ groups[etcd_cluster_group] }}"
```

## Makefile Targets

This repository includes a `Makefile` with common operations:

```bash
make create-cluster   # ansible-playbook etcd.yaml -e etcd_action=create
make upgrade-cluster  # ansible-playbook etcd.yaml -e etcd_action=upgrade
make delete-cluster   # ansible-playbook etcd.yaml -e etcd_delete_cluster=true
make docs            # mkdocs serve (documentation)
```

## Related Documentation

- [Inventory Configuration](../installation/inventory.md) - Detailed inventory setup
- [Variables Reference](variables.md) - All configurable variables
- [Role Structure](architecture.md) - Detailed role architecture
