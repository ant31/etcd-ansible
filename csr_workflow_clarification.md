# CSR-Based Certificate Workflow - Detailed Clarification

## Critical Concepts

### 1. "Local" Means ON THE ETCD NODE - NOT Your Laptop!

**WRONG Understanding:**
- ❌ Ansible controller (your laptop) generates keys
- ❌ Keys are generated on some "local" machine separate from etcd
- ❌ "Local" means the Ansible control machine

**CORRECT Understanding:**
- ✅ "Local" means ON THE ETCD/CLIENT NODE ITSELF
- ✅ Each etcd node generates its OWN keys ON ITSELF
- ✅ Ansible SSH's to the node and runs `openssl genrsa` ON THAT NODE
- ✅ Private keys are created and stay on the target node

### 2. Cert-Manager is an ETCD NODE - Not a Separate Server!

**WRONG Understanding:**
- ❌ Cert-manager is a separate dedicated server
- ❌ Cert-manager is your laptop/Ansible controller
- ❌ Need a special machine just for certificates

**CORRECT Understanding:**
- ✅ Cert-manager is typically etcd-k8s-1 (first etcd node)
- ✅ It's a regular etcd node that ALSO holds the CA keys
- ✅ In inventory: `[etcd-cert-managers]` usually contains `etcd-k8s-1`
- ✅ CA keys are stored in `/etc/etcd/ssl/` on this node

### 3. CA Keys Stay on ETCD Nodes - Not on Your Laptop!

**WRONG Understanding:**
- ❌ CA keys stored on developer's laptop
- ❌ CA keys in git repository
- ❌ CA keys on Ansible controller

**CORRECT Understanding:**
- ✅ CA keys stored on etcd-k8s-1 in `/etc/etcd/ssl/peer-ca.key`
- ✅ CA keys can be backed up to etcd-k8s-2, etcd-k8s-3 for redundancy
- ✅ CA keys can be backed up to encrypted object storage (S3, etc.)
- ✅ Ansible NEVER stores CA keys on disk (only in memory during playbook execution)

---

## Complete Workflow Example

### Cluster Setup
```
etcd-k8s-1: 10.0.1.10  (etcd node + cert-manager - holds CA keys)
etcd-k8s-2: 10.0.1.11  (etcd node only)
etcd-k8s-3: 10.0.1.12  (etcd node only)
app-server: 10.0.2.50  (client node - needs client cert)
```

### Inventory File
```ini
[etcd]
etcd-k8s-1 ansible_host=10.0.1.10
etcd-k8s-2 ansible_host=10.0.1.11
etcd-k8s-3 ansible_host=10.0.1.12

[etcd-clients]
app-server ansible_host=10.0.2.50

[etcd-cert-managers]
etcd-k8s-1  # This etcd node will hold the CA keys
```

---

## Phase 1: CA Initialization (One Time)

### You Run (from your laptop):
```bash
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create
```

### What Actually Happens:

```
┌─────────────────────────────────────────────────────────┐
│ Your Laptop (Ansible Controller)                        │
│ - Reads playbook and inventory                          │
│ - SSH to etcd-k8s-1                                     │
└─────────────────────────────────────────────────────────┘
                    │
                    │ SSH
                    ▼
┌─────────────────────────────────────────────────────────┐
│ etcd-k8s-1 (10.0.1.10) - The Cert-Manager Node          │
│                                                          │
│ Ansible runs these commands ON etcd-k8s-1:              │
│                                                          │
│ 1. Install cfssl binaries:                              │
│    wget https://.../cfssl → /opt/bin/cfssl              │
│    wget https://.../cfssljson → /opt/bin/cfssljson      │
│                                                          │
│ 2. Create CA keys ON etcd-k8s-1:                        │
│    cd /etc/etcd/ssl/                                    │
│    cfssl gencert -initca peer-ca-csr.json \             │
│      | cfssljson -bare peer-ca                          │
│                                                          │
│    Creates:                                             │
│    - /etc/etcd/ssl/peer-ca.key   (private - STAYS HERE)│
│    - /etc/etcd/ssl/peer-ca.crt   (public)               │
│                                                          │
│ 3. Same for client CA:                                  │
│    cfssl gencert -initca client-ca-csr.json \           │
│      | cfssljson -bare client-ca                        │
│                                                          │
│    Creates:                                             │
│    - /etc/etcd/ssl/client-ca.key (private - STAYS HERE)│
│    - /etc/etcd/ssl/client-ca.crt (public)               │
│                                                          │
│ 4. Set permissions:                                     │
│    chmod 0400 /etc/etcd/ssl/*-ca.key                    │
│    chown root:root /etc/etcd/ssl/*-ca.key               │
└─────────────────────────────────────────────────────────┘
```

### Result:
- ✅ CA keys exist ONLY on etcd-k8s-1 (at `/etc/etcd/ssl/`)
- ✅ Your laptop has NO CA keys
- ✅ CA keys are owned by root, mode 0400 (read-only by root)

---

## Phase 2: Certificate Generation for etcd-k8s-2

### Same Command (from your laptop):
```bash
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create
```

### Step 1: Generate Private Key ON etcd-k8s-2

```
┌─────────────────────────────────────────────────────────┐
│ Your Laptop (Ansible Controller)                        │
│ - SSH to etcd-k8s-2                                     │
└─────────────────────────────────────────────────────────┘
                    │
                    │ SSH
                    ▼
┌─────────────────────────────────────────────────────────┐
│ etcd-k8s-2 (10.0.1.11) - Target Node                    │
│                                                          │
│ Ansible runs ON etcd-k8s-2:                             │
│                                                          │
│ - name: Generate peer private key                       │
│   command: |                                            │
│     openssl genrsa -out \                               │
│       /etc/etcd/ssl/etcd-k8s-2-peer.key 2048            │
│                                                          │
│ THIS COMMAND RUNS ON etcd-k8s-2!                        │
│ The key is created ON etcd-k8s-2!                       │
│ The key NEVER leaves etcd-k8s-2!                        │
│                                                          │
│ Files created:                                          │
│ /etc/etcd/ssl/                                          │
│   ├── etcd-k8s-2-peer.key    (CREATED HERE, STAYS HERE)│
│   ├── etcd-k8s-2-server.key  (CREATED HERE, STAYS HERE)│
│   └── etcd-k8s-2-client.key  (CREATED HERE, STAYS HERE)│
└─────────────────────────────────────────────────────────┘
```

### Step 2: Create CSR ON etcd-k8s-2

```
┌─────────────────────────────────────────────────────────┐
│ etcd-k8s-2 (10.0.1.11)                                  │
│                                                          │
│ Ansible runs ON etcd-k8s-2:                             │
│                                                          │
│ - name: Create peer CSR config                          │
│   template:                                             │
│     src: peer-csr.json.j2                               │
│     dest: /etc/etcd/ssl/etcd-k8s-2-peer-csr.json        │
│   # Template includes etcd-k8s-2's IP: 10.0.1.11        │
│                                                          │
│ - name: Generate peer CSR                               │
│   command: |                                            │
│     cfssl gencert \                                     │
│       /etc/etcd/ssl/etcd-k8s-2-peer-csr.json \          │
│       | cfssljson -bare /etc/etcd/ssl/etcd-k8s-2-peer   │
│                                                          │
│ Creates:                                                │
│   /etc/etcd/ssl/etcd-k8s-2-peer.csr  (CSR file)         │
│                                                          │
│ CSR is PUBLIC data - safe to transmit                   │
└─────────────────────────────────────────────────────────┘
```

### Step 3: Transfer CSR to Ansible Controller (in memory)

```
┌─────────────────────────────────────────────────────────┐
│ Your Laptop (Ansible Controller)                        │
│                                                          │
│ - name: Fetch CSR from etcd-k8s-2                       │
│   slurp:                                                │
│     src: /etc/etcd/ssl/etcd-k8s-2-peer.csr              │
│   register: etcd_k8s_2_peer_csr                         │
│                                                          │
│ This reads the CSR file via SSH and stores it           │
│ in an Ansible variable (IN MEMORY ONLY)                 │
│                                                          │
│ CSR content is now in:                                  │
│   etcd_k8s_2_peer_csr.content (base64 encoded)          │
│                                                          │
│ NOTE: CSR is PUBLIC data, so this is safe!              │
└─────────────────────────────────────────────────────────┘
```

### Step 4: Transfer CSR to Cert-Manager and Sign

```
┌─────────────────────────────────────────────────────────┐
│ Your Laptop (Ansible Controller)                        │
│ - SSH to etcd-k8s-1 (cert-manager)                      │
│ - Copies CSR content from memory to etcd-k8s-1          │
└─────────────────────────────────────────────────────────┘
                    │
                    │ SSH + copy CSR
                    ▼
┌─────────────────────────────────────────────────────────┐
│ etcd-k8s-1 (10.0.1.10) - Cert-Manager Node              │
│                                                          │
│ Ansible runs ON etcd-k8s-1:                             │
│                                                          │
│ - name: Copy CSR to cert-manager                        │
│   copy:                                                 │
│     content: "{{ etcd_k8s_2_peer_csr.content|b64decode}}"│
│     dest: /etc/etcd/ssl/etcd-k8s-2-peer.csr             │
│   delegate_to: etcd-k8s-1                               │
│                                                          │
│ - name: Sign CSR with CA                                │
│   command: |                                            │
│     cfssl sign \                                        │
│       -ca=/etc/etcd/ssl/peer-ca.crt \                   │
│       -ca-key=/etc/etcd/ssl/peer-ca.key \               │
│       -config=/etc/etcd/ssl/peer-ca-config.json \       │
│       -profile=peer \                                   │
│       /etc/etcd/ssl/etcd-k8s-2-peer.csr \               │
│       | cfssljson -bare /etc/etcd/ssl/etcd-k8s-2-peer   │
│   delegate_to: etcd-k8s-1                               │
│                                                          │
│ Creates:                                                │
│   /etc/etcd/ssl/etcd-k8s-2-peer.crt (SIGNED CERT)       │
│                                                          │
│ NOTE: peer-ca.key is used HERE, on etcd-k8s-1!          │
│       peer-ca.key NEVER leaves etcd-k8s-1!              │
└─────────────────────────────────────────────────────────┘
```

### Step 5: Transfer Signed Cert Back to etcd-k8s-2

```
┌─────────────────────────────────────────────────────────┐
│ etcd-k8s-1 (Cert-Manager)                               │
│ Has: /etc/etcd/ssl/etcd-k8s-2-peer.crt                  │
└─────────────────────────────────────────────────────────┘
                    │
                    │ Ansible slurp (reads file via SSH)
                    ▼
┌─────────────────────────────────────────────────────────┐
│ Your Laptop (Ansible Controller) - IN MEMORY            │
│ etcd_k8s_2_peer_crt.content = "signed cert (base64)"    │
└─────────────────────────────────────────────────────────┘
                    │
                    │ Ansible copy (writes file via SSH)
                    ▼
┌─────────────────────────────────────────────────────────┐
│ etcd-k8s-2 (Target Node)                                │
│                                                          │
│ Ansible runs ON etcd-k8s-2:                             │
│                                                          │
│ - name: Install signed cert                             │
│   copy:                                                 │
│     content: "{{ etcd_k8s_2_peer_crt.content|b64decode}}"│
│     dest: /etc/etcd/ssl/etcd-k8s-2-peer.crt             │
│     owner: etcd                                         │
│     mode: 0644                                          │
│                                                          │
│ Final files on etcd-k8s-2:                              │
│ /etc/etcd/ssl/                                          │
│   ├── etcd-k8s-2-peer.key  (0400) GENERATED ON THIS NODE│
│   ├── etcd-k8s-2-peer.crt  (0644) FROM CERT-MANAGER     │
│   ├── peer-ca.crt          (0644) FROM CERT-MANAGER     │
│   └── ...                                               │
└─────────────────────────────────────────────────────────┘
```

---

## Security Summary

### What NEVER Leaves Its Origin Node:
1. ✅ **peer-ca.key** - stays on etcd-k8s-1 (cert-manager)
2. ✅ **client-ca.key** - stays on etcd-k8s-1 (cert-manager)
3. ✅ **etcd-k8s-2-peer.key** - stays on etcd-k8s-2
4. ✅ **etcd-k8s-2-server.key** - stays on etcd-k8s-2
5. ✅ **etcd-k8s-2-client.key** - stays on etcd-k8s-2
6. ✅ **etcd-k8s-3-*.key** - stays on etcd-k8s-3
7. ✅ **app-server-client.key** - stays on app-server

### What Gets Transmitted (All PUBLIC Data - Safe):
1. ✅ CSRs (Certificate Signing Requests) - public data
2. ✅ Signed certificates (.crt files) - public data
3. ✅ CA certificates (.crt files) - public data

### Where Data Flows:
```
etcd-k8s-2 (private key stays here)
    │
    │ CSR (public) via Ansible/SSH
    ▼
Ansible Controller (CSR in memory only)
    │
    │ CSR (public) via Ansible/SSH
    ▼
etcd-k8s-1 (signs with CA key that stays here)
    │
    │ Signed cert (public) via Ansible/SSH
    ▼
Ansible Controller (cert in memory only)
    │
    │ Signed cert (public) via Ansible/SSH
    ▼
etcd-k8s-2 (receives signed cert, has its private key)
```

---

## CA Redundancy: What If etcd-k8s-1 Dies?

### Option 1: Multiple Cert-Managers (Recommended)

**Setup:**
```ini
[etcd-cert-managers]
etcd-k8s-1  # Primary
etcd-k8s-2  # Backup (gets copy of CA keys)
etcd-k8s-3  # Backup (gets copy of CA keys)
```

**Initial Setup:**
```bash
# 1. Create CA on etcd-k8s-1 (normal)
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create

# 2. Backup CA keys to other nodes
ansible-playbook -i inventory.ini backup-ca-keys.yaml
```

**What backup-ca-keys.yaml does:**
```yaml
- hosts: etcd-k8s-1
  tasks:
    - name: Read CA keys
      slurp:
        src: "/etc/etcd/ssl/{{ item }}"
      register: ca_keys
      loop:
        - peer-ca.key
        - client-ca.key
      no_log: true  # Don't log private keys

- hosts: etcd-cert-managers
  tasks:
    - name: Install CA keys
      copy:
        content: "{{ item.content | b64decode }}"
        dest: "/etc/etcd/ssl/{{ item.item }}"
        owner: root
        mode: 0400
      loop: "{{ hostvars['etcd-k8s-1']['ca_keys'].results }}"
      no_log: true
```

**Now if etcd-k8s-1 dies:**
- Change inventory: `[etcd-cert-managers]` → `etcd-k8s-2`
- etcd-k8s-2 already has CA keys
- No disruption to certificate signing

### Option 2: Encrypted Backup to S3

```yaml
- hosts: etcd-k8s-1
  tasks:
    - name: Create encrypted CA backup
      shell: |
        tar czf - /etc/etcd/ssl/*-ca.key | \
        gpg --encrypt --recipient ops@example.com > /tmp/ca-backup.tar.gz.gpg

    - name: Upload to S3
      aws_s3:
        bucket: etcd-backups
        object: "ca-keys/{{ etcd_cluster_name }}-ca-{{ ansible_date_time.date }}.tar.gz.gpg"
        src: /tmp/ca-backup.tar.gz.gpg
        encrypt: yes
```

**To restore on new cert-manager:**
```bash
# Download backup
aws s3 cp s3://etcd-backups/ca-keys/... /tmp/ca-backup.tar.gz.gpg

# Decrypt and extract
gpg --decrypt /tmp/ca-backup.tar.gz.gpg | tar xzf - -C /

# Set permissions
chmod 0400 /etc/etcd/ssl/*-ca.key
```

---

## Adding New Node (etcd-k8s-4)

### Updated Inventory:
```ini
[etcd]
etcd-k8s-1
etcd-k8s-2
etcd-k8s-3
etcd-k8s-4  # NEW NODE

[etcd-cert-managers]
etcd-k8s-1  # Still the same CA
```

### Run Playbook (same as before):
```bash
ansible-playbook -i inventory.ini etcd.yaml -e etcd_action=create --limit=etcd-k8s-4
```

### What Happens:

1. **ON etcd-k8s-4** - Generate private keys:
   ```
   openssl genrsa -out /etc/etcd/ssl/etcd-k8s-4-peer.key 2048
   openssl genrsa -out /etc/etcd/ssl/etcd-k8s-4-server.key 2048
   openssl genrsa -out /etc/etcd/ssl/etcd-k8s-4-client.key 2048
   ```

2. **ON etcd-k8s-4** - Create CSRs:
   ```
   cfssl gencert ... | cfssljson -bare etcd-k8s-4-peer
   # Creates etcd-k8s-4-peer.csr
   ```

3. **Transfer CSR** (public data) to Ansible Controller

4. **ON etcd-k8s-1** (cert-manager) - Sign with EXISTING CA:
   ```
   cfssl sign -ca=peer-ca.crt -ca-key=peer-ca.key ...
   # Uses SAME CA as other nodes!
   # NO new CA created!
   ```

5. **Transfer signed cert** back to etcd-k8s-4

6. **ON etcd-k8s-4** - Join cluster with new certs

### Key Points:
- ✅ CA stays the same (on etcd-k8s-1)
- ✅ Only etcd-k8s-4 gets new leaf certificates
- ✅ etcd-k8s-4's private keys NEVER leave etcd-k8s-4
- ✅ CA keys NEVER leave etcd-k8s-1

---

## Common Misunderstandings - CORRECTED

### ❌ "The developer laptop has the CA keys"
**✅ CORRECT:** CA keys are on etcd-k8s-1 (cert-manager node), not your laptop

### ❌ "Ansible stores private keys"
**✅ CORRECT:** Ansible only holds public data (CSRs, certs) in memory during execution

### ❌ "Local means on my laptop"
**✅ CORRECT:** "Local" means on the target node itself (etcd-k8s-2 generates keys ON etcd-k8s-2)

### ❌ "Cert-manager is a separate service"
**✅ CORRECT:** Cert-manager is just etcd-k8s-1 (an etcd node that also holds CA keys)

### ❌ "CA keys get transmitted to nodes"
**✅ CORRECT:** Only CA certificates (.crt) are distributed, never CA private keys (.key)

### ❌ "Adding a node requires rotating the CA"
**✅ CORRECT:** New nodes use the EXISTING CA, only new leaf certs are created

### ❌ "If etcd-k8s-1 dies, we lose the CA"
**✅ CORRECT:** Backup CA keys to other etcd nodes or encrypted storage for redundancy

---

## Verification Commands

### On etcd-k8s-1 (cert-manager):
```bash
# CA keys should exist and be owned by root
ls -la /etc/etcd/ssl/*-ca.key
# Should show: -r-------- 1 root root ... peer-ca.key

# CA keys should never be readable by others
stat -c '%a %U' /etc/etcd/ssl/peer-ca.key
# Should show: 400 root
```

### On etcd-k8s-2 (regular node):
```bash
# Should have its OWN private keys
ls -la /etc/etcd/ssl/etcd-k8s-2-*.key
# Should exist and be 0400

# Should NOT have CA private keys
ls /etc/etcd/ssl/*-ca.key
# Should show: No such file or directory

# Should have CA certificates (public)
ls -la /etc/etcd/ssl/*-ca.crt
# Should exist and be 0644
```

### On your laptop:
```bash
# Should NOT have any private keys
find ~/.ansible /tmp -name '*-ca.key' -o -name 'etcd-*.key'
# Should return nothing (or only temporary files in /tmp that get cleaned up)
```

---

## Summary Diagram

```
┌────────────────────────────────────────────────────────────────┐
│  YOUR UNDERSTANDING SHOULD BE:                                 │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Your Laptop (Ansible Controller)                           │
│     - Runs playbooks                                           │
│     - SSH to all nodes                                         │
│     - Moves public data (CSRs, certs) between nodes            │
│     - NEVER stores private keys on disk                        │
│                                                                 │
│  2. etcd-k8s-1 (Cert-Manager = etcd node)                      │
│     - Regular etcd node                                        │
│     - ALSO holds CA keys (peer-ca.key, client-ca.key)          │
│     - Signs CSRs from other nodes                              │
│     - CA keys: /etc/etcd/ssl/*-ca.key (mode 0400, owner root)  │
│                                                                 │
│  3. etcd-k8s-2, etcd-k8s-3 (Regular etcd nodes)                │
│     - Generate their OWN private keys ON THEMSELVES            │
│     - Create CSRs ON THEMSELVES                                │
│     - Receive signed certs from cert-manager                   │
│     - Receive CA certs (public only)                           │
│     - DO NOT have CA private keys                              │
│                                                                 │
│  4. Flow for new cert:                                         │
│     Node generates key → Node creates CSR →                    │
│     Ansible moves CSR to cert-manager →                        │
│     Cert-manager signs CSR →                                   │
│     Ansible moves signed cert back to node →                   │
│     Node uses cert with its private key                        │
│                                                                 │
│  5. Security guarantees:                                       │
│     ✅ Private keys NEVER transmitted                          │
│     ✅ CA keys NEVER leave cert-manager                        │
│     ✅ Node keys NEVER leave their nodes                       │
│     ✅ Only public data moves via Ansible                      │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```
