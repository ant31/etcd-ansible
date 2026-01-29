# Load Balancer Integration

This guide explains how to deploy etcd behind a load balancer for stable client connectivity.

## Why Use a Load Balancer?

**Benefits:**
- ✅ **Stable endpoint**: Clients use single IP/hostname instead of all node IPs
- ✅ **Easier maintenance**: Add/remove etcd nodes without updating client configurations
- ✅ **Automatic failover**: LB routes around failed nodes
- ✅ **Service discovery**: Single DNS name for the entire cluster

**Important:** Only **client traffic** (port 2379) goes through LB. Peer communication (port 2380) must stay direct for Raft consensus.

## Architecture

### Without Load Balancer (Default)
```
Client → https://10.0.1.10:2379,https://10.0.1.11:2379,https://10.0.1.12:2379
         ↓ Client handles failover between nodes
         etcd-1, etcd-2, etcd-3
```

### With Load Balancer
```
Client → https://etcd-lb.example.com:2379
         ↓ Load balancer (TLS passthrough)
         etcd-1:2379, etcd-2:2379, etcd-3:2379
         ↓ Peer communication stays direct (no LB)
         etcd-1:2380 ↔ etcd-2:2380 ↔ etcd-3:2380
```

## Load Balancer Modes

### Mode 1: TLS Passthrough (RECOMMENDED) ✅

**How it works:**
- LB forwards encrypted traffic without decrypting (Layer 4)
- TLS handshake: Client ↔ etcd node (direct)
- LB just routes TCP packets

**Certificate requirements:**
- etcd server certificates must include LB hostname/IP in SANs
- No LB certificate needed

**Configuration:**
```yaml
# group_vars/all/etcd.yaml or inventory
etcd_lb_enabled: true
etcd_lb_host: "etcd-lb.internal.example.com"
etcd_lb_ip: "10.0.1.100"  # Optional VIP

# Add LB to server certificate SANs
etcd_cert_alt_names:
  - "{{ etcd_lb_host }}"
  - "etcd.kube-system.svc.cluster.local"

etcd_cert_alt_ips:
  - "{{ etcd_lb_ip }}"
```

**Pros:**
- ✅ LB never sees plaintext (most secure)
- ✅ No LB certificate management
- ✅ Simple configuration

**Cons:**
- ⚠️  LB can't inspect traffic
- ⚠️  Health checks must be TCP-based

---

### Mode 2: TLS Termination (Advanced) ⚠️

**How it works:**
- LB terminates client TLS (decrypts)
- LB initiates new TLS to etcd (re-encrypts)

**Certificate requirements:**
- LB needs client certificate (from step-ca)
- LB needs server certificate (for clients)
- etcd keeps current certificates

**Pros:**
- ✅ LB can inspect traffic
- ✅ Advanced health checks

**Cons:**
- ❌ More complex certificate management
- ❌ LB sees plaintext (security concern)
- ❌ Performance overhead

**We focus on TLS Passthrough (Mode 1) in this guide.**

---

## Setup Instructions

### 1. Configure Load Balancer Variables

Add to your `inventory.ini` or `group_vars/all/etcd.yaml`:

```yaml
# Enable load balancer mode
etcd_lb_enabled: true

# Load balancer endpoint
etcd_lb_host: "etcd-lb.internal.example.com"
etcd_lb_port: 2379  # Optional, defaults to etcd client port

# Load balancer IP (optional but recommended)
etcd_lb_ip: "10.0.1.100"

# Add LB to server certificate SANs
etcd_cert_alt_names:
  - "{{ etcd_lb_host }}"
  - "etcd.kube-system.svc.{{ dns_domain }}"
  - "etcd.kube-system.svc"
  - "etcd"

etcd_cert_alt_ips:
  - "{{ etcd_lb_ip }}"
```

### 2. Regenerate Server Certificates with LB SANs

```bash
# Regenerate certificates to include LB in SANs
ansible-playbook -i inventory.ini playbooks/regenerate-node-certs.yaml
```

This regenerates server certificates with the LB hostname/IP included.

### 3. Verify Certificates Include LB SAN

```bash
# Check server certificate SANs
ansible etcd -i inventory.ini -m shell -a \
  "step certificate inspect /etc/etcd/ssl/etcd-*-server.crt | grep -A20 'X509v3 Subject Alternative Name'" -b
```

Expected output should include:
```
X509v3 Subject Alternative Name:
    DNS:etcd-lb.internal.example.com
    DNS:etcd.kube-system.svc.cluster.local
    IP Address:10.0.1.100
    IP Address:10.0.1.10
    IP Address:127.0.0.1
    ...
```

### 4. Configure Your Load Balancer

#### HAProxy Example (TLS Passthrough)

```haproxy
# /etc/haproxy/haproxy.cfg

global
    log /dev/log local0
    maxconn 4096

defaults
    log global
    mode tcp
    timeout connect 10s
    timeout client 5m
    timeout server 5m

frontend etcd-client-frontend
    bind *:2379
    mode tcp
    default_backend etcd-cluster

backend etcd-cluster
    mode tcp
    balance roundrobin
    option tcp-check
    server etcd-1 10.0.1.10:2379 check
    server etcd-2 10.0.1.11:2379 check
    server etcd-3 10.0.1.12:2379 check
```

**Health check options:**
```haproxy
# Option 1: TCP check (simple, always works)
option tcp-check

# Option 2: HTTPS health endpoint (better)
option httpchk GET /health
http-check expect status 200

# Option 3: etcd-specific health check (requires SSL)
option httpchk GET /health
http-check send-state
```

#### NGINX Example (TLS Passthrough)

```nginx
# /etc/nginx/nginx.conf

stream {
    upstream etcd_cluster {
        server 10.0.1.10:2379 max_fails=3 fail_timeout=30s;
        server 10.0.1.11:2379 max_fails=3 fail_timeout=30s;
        server 10.0.1.12:2379 max_fails=3 fail_timeout=30s;
    }

    server {
        listen 2379;
        proxy_pass etcd_cluster;
        proxy_connect_timeout 10s;
        proxy_timeout 5m;
    }
}
```

#### Cloud Load Balancer Examples

**AWS Network Load Balancer (NLB):**
```bash
# Create target group
aws elbv2 create-target-group \
  --name etcd-cluster \
  --protocol TCP \
  --port 2379 \
  --vpc-id vpc-xxxxx \
  --health-check-protocol TCP \
  --health-check-port 2379

# Register targets
aws elbv2 register-targets \
  --target-group-arn arn:... \
  --targets Id=i-xxx1 Id=i-xxx2 Id=i-xxx3

# Create NLB
aws elbv2 create-load-balancer \
  --name etcd-lb \
  --type network \
  --subnets subnet-xxx \
  --scheme internal
```

**GCP Internal TCP/UDP Load Balancer:**
```bash
# Create health check
gcloud compute health-checks create tcp etcd-health \
  --port=2379

# Create backend service
gcloud compute backend-services create etcd-backend \
  --protocol=TCP \
  --health-checks=etcd-health \
  --region=us-central1

# Add instances
gcloud compute backend-services add-backend etcd-backend \
  --instance-group=etcd-ig \
  --region=us-central1

# Create forwarding rule
gcloud compute forwarding-rules create etcd-lb \
  --load-balancing-scheme=INTERNAL \
  --backend-service=etcd-backend \
  --ports=2379 \
  --region=us-central1
```

### 5. Test Client Connectivity Through LB

```bash
# From a client node
etcdctl --endpoints=https://etcd-lb.example.com:2379 \
  --cert=/etc/etcd/ssl/etcd-client.crt \
  --key=/etc/etcd/ssl/etcd-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint health

# Should return:
# https://etcd-lb.example.com:2379 is healthy: successfully committed proposal
```

### 6. Update Application Configurations

Kubernetes API server example:

```yaml
# kube-apiserver.yaml
spec:
  containers:
  - name: kube-apiserver
    command:
    - kube-apiserver
    # OLD: --etcd-servers=https://10.0.1.10:2379,https://10.0.1.11:2379,https://10.0.1.12:2379
    # NEW: Single stable endpoint
    - --etcd-servers={{ etcd_lb_address }}  # Automatically set when etcd_lb_enabled=true
    - --etcd-cafile={{ etcd_cert_paths.client.ca }}
    - --etcd-certfile={{ etcd_cert_paths.client.cert }}
    - --etcd-keyfile={{ etcd_cert_paths.client.key }}
```

---

## Available Connection Variables

When `etcd_lb_enabled=true`, the facts role provides:

```yaml
# Automatically uses LB when enabled, otherwise direct node URLs
etcd_access_addresses: "https://etcd-lb.example.com:2379"

# Explicit LB address (always set when etcd_lb_enabled=true)
etcd_lb_address: "https://etcd-lb.example.com:2379"

# Direct node URLs (always available, bypasses LB)
etcd_access_addresses_direct: "https://10.0.1.10:2379,https://10.0.1.11:2379,https://10.0.1.12:2379"

# Peer URLs (never use LB - always direct)
etcd_peer_addresses: "etcd-1=https://10.0.1.10:2380,etcd-2=https://10.0.1.11:2380,..."
```

**Usage in templates:**
```yaml
# Use LB when available, fall back to direct
etcd_servers: "{{ etcd_access_addresses }}"

# Always use LB (fails if not configured)
etcd_servers: "{{ etcd_lb_address }}"

# Bypass LB (troubleshooting)
etcd_servers: "{{ etcd_access_addresses_direct }}"
```

---

## Troubleshooting

### TLS Handshake Failure

**Symptom:**
```
Error: remote error: tls: bad certificate
# or
Error: x509: certificate is valid for 10.0.1.10, not etcd-lb.example.com
```

**Cause:** Server certificate doesn't include LB hostname/IP in SANs.

**Fix:**
```bash
# 1. Verify LB variables are set
ansible-inventory -i inventory.ini --host etcd-1 | grep etcd_lb

# 2. Check current certificate SANs
ansible etcd -i inventory.ini -m shell -a \
  "step certificate inspect /etc/etcd/ssl/etcd-*-server.crt | grep -A10 'Subject Alternative Name'" -b

# 3. Regenerate with LB SANs
ansible-playbook -i inventory.ini playbooks/regenerate-node-certs.yaml

# 4. Verify new SANs include LB
ansible etcd -i inventory.ini -m shell -a \
  "step certificate inspect /etc/etcd/ssl/etcd-*-server.crt | grep 'etcd-lb'" -b
```

### Connection Timeout Through LB

**Symptom:**
```
Error: context deadline exceeded
```

**Possible causes:**
1. LB health checks failing → backends marked down
2. Network/firewall blocking traffic
3. LB timeout too short

**Fix:**
```bash
# 1. Check LB backend health
# HAProxy: http://lb-admin:9000/stats
# NGINX: check logs
# Cloud: Check console

# 2. Test direct connection (bypass LB)
etcdctl --endpoints=https://10.0.1.10:2379 endpoint health

# 3. Check if LB can reach backends
# From LB host:
telnet 10.0.1.10 2379
curl -k https://10.0.1.10:2379/health

# 4. Increase LB timeouts
# HAProxy: timeout client 5m / timeout server 5m
# NGINX: proxy_timeout 5m
```

### Clients Still Using Old Direct Endpoints

**Symptom:** Clients connect to node IPs instead of LB.

**Cause:** Configuration not updated or cached.

**Fix:**
```bash
# 1. Verify facts show LB address
ansible etcd -i inventory.ini -m debug -a "var=etcd_access_addresses"
# Should show: https://etcd-lb.example.com:2379 (not node IPs)

# 2. Re-run playbooks to update client configs
ansible-playbook -i inventory.ini playbooks/generate-client-certs.yaml

# 3. For Kubernetes, restart controllers to refresh
kubectl rollout restart deployment -n kube-system
```

---

## Best Practices

### 1. Use TLS Passthrough

Always prefer Layer 4 TLS passthrough over TLS termination for etcd:
- More secure (LB never sees plaintext)
- Simpler certificate management
- Better performance

### 2. Set Appropriate Timeouts

```haproxy
# HAProxy example
timeout client 5m
timeout server 5m
timeout connect 10s
```

Long-lived connections (watches) need higher timeouts.

### 3. Health Check Configuration

```haproxy
# Simple TCP check (always works)
option tcp-check

# Or HTTPS health endpoint (better)
option httpchk GET /health
http-check expect status 200
```

Don't check `/version` - use `/health` which verifies cluster health.

### 4. Monitor Backend Health

- Set up alerting when backends go down
- Use LB statistics page (HAProxy, NGINX Plus)
- Export metrics to Prometheus/CloudWatch

### 5. Plan for LB Failure

Even with LB:
- Keep direct node URLs documented
- Test failover to direct connection
- Have runbooks for LB failure

**Emergency bypass:**
```bash
# Temporarily use direct connection
kubectl edit deployment kube-apiserver
# Change: --etcd-servers=https://etcd-lb:2379
# To:     --etcd-servers=https://10.0.1.10:2379,https://10.0.1.11:2379,https://10.0.1.12:2379
```

---

## Migration Guide

### Step 1: Deploy Load Balancer

Set up your LB infrastructure (HAProxy, NGINX, cloud LB).

### Step 2: Configure Variables

```yaml
# inventory.ini or group_vars/all/etcd.yaml
etcd_lb_enabled: true
etcd_lb_host: "etcd-lb.internal.example.com"
etcd_lb_ip: "10.0.1.100"

etcd_cert_alt_names:
  - "{{ etcd_lb_host }}"

etcd_cert_alt_ips:
  - "{{ etcd_lb_ip }}"
```

### Step 3: Regenerate Certificates

```bash
# Regenerate with LB SANs
ansible-playbook -i inventory.ini playbooks/regenerate-node-certs.yaml
```

### Step 4: Verify

```bash
# Check certificate SANs
ansible etcd -i inventory.ini -m shell -a \
  "step certificate inspect /etc/etcd/ssl/etcd-*-server.crt | grep etcd-lb" -b

# Check facts use LB address
ansible etcd[0] -i inventory.ini -m debug -a "var=etcd_access_addresses"
```

### Step 5: Update Clients

```bash
# Update client certificates/configs
ansible-playbook -i inventory.ini playbooks/generate-client-certs.yaml

# For Kubernetes
kubectl rollout restart deployment -n kube-system
```

### Step 6: Test Connectivity

```bash
# Test through LB
etcdctl --endpoints=https://etcd-lb.example.com:2379 \
  --cert=/etc/etcd/ssl/etcd-client.crt \
  --key=/etc/etcd/ssl/etcd-client.key \
  --cacert=/etc/etcd/ssl/root_ca.crt \
  endpoint health

# Verify direct access still works (for troubleshooting)
etcdctl --endpoints=https://10.0.1.10:2379 endpoint health
```

---

## Example Configurations

### HAProxy (Production)

```haproxy
# /etc/haproxy/haproxy.cfg

global
    log /dev/log local0
    log /dev/log local1 notice
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    stats timeout 30s
    user haproxy
    group haproxy
    daemon
    maxconn 4096

defaults
    log global
    mode tcp
    option tcplog
    option dontlognull
    timeout connect 10s
    timeout client 5m
    timeout server 5m

# Statistics page
listen stats
    bind *:9000
    mode http
    stats enable
    stats uri /stats
    stats refresh 10s
    stats auth admin:password

# Etcd client frontend
frontend etcd-client
    bind *:2379
    mode tcp
    default_backend etcd-cluster

# Etcd backend with health checks
backend etcd-cluster
    mode tcp
    balance roundrobin
    option tcp-check

    server etcd-1 10.0.1.10:2379 check inter 10s fall 3 rise 2
    server etcd-2 10.0.1.11:2379 check inter 10s fall 3 rise 2
    server etcd-3 10.0.1.12:2379 check inter 10s fall 3 rise 2
```

### NGINX Plus (with Active Health Checks)

```nginx
# /etc/nginx/nginx.conf

stream {
    upstream etcd_cluster {
        least_conn;

        server 10.0.1.10:2379 max_fails=3 fail_timeout=30s;
        server 10.0.1.11:2379 max_fails=3 fail_timeout=30s;
        server 10.0.1.12:2379 max_fails=3 fail_timeout=30s;

        # NGINX Plus only: active health check
        # health_check interval=10s passes=2 fails=3;
    }

    server {
        listen 2379;
        proxy_pass etcd_cluster;
        proxy_connect_timeout 10s;
        proxy_timeout 5m;

        # Enable TCP keepalive
        proxy_socket_keepalive on;
    }
}
```

### AWS Network Load Balancer (Terraform)

```hcl
# etcd-nlb.tf

resource "aws_lb" "etcd" {
  name               = "etcd-lb"
  internal           = true
  load_balancer_type = "network"
  subnets            = var.private_subnets

  enable_deletion_protection = true
  enable_cross_zone_load_balancing = true

  tags = {
    Name = "etcd-cluster-lb"
  }
}

resource "aws_lb_target_group" "etcd_client" {
  name     = "etcd-client-tg"
  port     = 2379
  protocol = "TCP"
  vpc_id   = var.vpc_id

  health_check {
    protocol            = "TCP"
    port                = 2379
    interval            = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 30
}

resource "aws_lb_target_group_attachment" "etcd_nodes" {
  count            = 3
  target_group_arn = aws_lb_target_group.etcd_client.arn
  target_id        = element(aws_instance.etcd.*.id, count.index)
  port             = 2379
}

resource "aws_lb_listener" "etcd_client" {
  load_balancer_arn = aws_lb.etcd.arn
  port              = 2379
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.etcd_client.arn
  }
}

output "etcd_lb_dns" {
  value = aws_lb.etcd.dns_name
}
```

---

## Security Considerations

### 1. Certificate Validation

With LB, clients validate against the **LB hostname**, so:
- ✅ Server cert MUST include LB in SANs
- ✅ Clients trust the same root CA
- ❌ Don't disable certificate validation (`--insecure-skip-tls-verify`)

### 2. Backend Access Control

Restrict direct access to etcd nodes:

```bash
# Firewall example (only allow LB to access etcd)
iptables -A INPUT -p tcp --dport 2379 -s 10.0.1.100 -j ACCEPT  # LB
iptables -A INPUT -p tcp --dport 2379 -j DROP  # Block all others

# Port 2380 (peer) should only allow other etcd nodes
iptables -A INPUT -p tcp --dport 2380 -s 10.0.1.0/24 -j ACCEPT  # etcd subnet
iptables -A INPUT -p tcp --dport 2380 -j DROP
```

### 3. LB High Availability

Single LB is a SPOF. Options:

**Option 1: HA Load Balancer Pair**
- Active/passive HAProxy with Keepalived
- Virtual IP (VIP) floats between LBs
- Use VIP as `etcd_lb_ip`

**Option 2: Cloud Load Balancers**
- AWS NLB: Multi-AZ by default
- GCP ILB: Regional, automatically HA
- Azure LB: Zone-redundant

**Option 3: DNS-based Failover**
- Multiple LB instances
- DNS A records with health checks (Route53, CloudDNS)
- Client DNS timeout must be low

### 4. Monitoring

**Monitor:**
- LB backend health (how many nodes up?)
- LB connection count (are clients connecting?)
- LB error rate (connection failures?)
- End-to-end client latency through LB

**Alerts:**
```yaml
# Prometheus example
- alert: EtcdLoadBalancerBackendDown
  expr: haproxy_backend_up{backend="etcd-cluster"} < 2
  for: 5m
  annotations:
    summary: "Etcd LB has fewer than 2 healthy backends"
```

---

## Performance Impact

### Latency

**Expected overhead:**
- TLS passthrough: < 1ms (just TCP routing)
- TLS termination: 2-5ms (decrypt + re-encrypt)

**Measurement:**
```bash
# Direct connection baseline
time etcdctl --endpoints=https://10.0.1.10:2379 get /test

# Through LB
time etcdctl --endpoints=https://etcd-lb:2379 get /test
```

### Throughput

Layer 4 passthrough has minimal impact:
- Modern LBs: 10-100 Gbps
- etcd cluster: Typically < 1 Gbps

---

## Limitations

### What Load Balancer Does NOT Solve

1. **Split Brain:** If network partitions, LB can't fix quorum
2. **Data Consistency:** LB doesn't make etcd more consistent
3. **Performance:** LB doesn't make etcd faster (adds tiny latency)

### What Load Balancer DOES Solve

1. ✅ **Stable endpoint:** Single IP/DNS instead of list
2. ✅ **Automatic routing:** LB routes around failed nodes
3. ✅ **Easier operations:** Add/remove nodes without client changes

---

## Example Inventory

```ini
# inventory.ini

[etcd]
etcd-1 ansible_host=10.0.1.10
etcd-2 ansible_host=10.0.1.11
etcd-3 ansible_host=10.0.1.12

[etcd-clients]
kube-apiserver-1 ansible_host=10.0.2.10

[etcd-cert-managers]
etcd-1

[all:vars]
# Load balancer configuration
etcd_lb_enabled=true
etcd_lb_host=etcd-lb.internal.example.com
etcd_lb_ip=10.0.1.100

# Add LB to server certs
etcd_cert_alt_names=['{{ etcd_lb_host }}', 'etcd.kube-system.svc.cluster.local']
etcd_cert_alt_ips=['{{ etcd_lb_ip }}']
```

---

## See Also

- [Certificate Architecture](../certificates/overview.md)
- [HA Setup](ha-setup.md)
- [Health Checks](../operations/health-checks.md)
- [Scaling Guide](../operations/scaling.md)
