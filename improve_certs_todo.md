# Certificate Management Improvement TODO

## Current State Analysis

### Problems with Current Implementation
1. **Centralized Private Key Generation** - All private keys are generated on cert-manager host, violating security best practices
2. **Complex Distribution** - Tarball-based distribution is error-prone and hard to debug
3. **Inconsistent Naming** - Files use `{{inventory_hostname}}-profile.pem` which can be long and inconsistent
4. **No Rotation Automation** - Manual rotation only via `etcd_rotate_certs=true`
5. **No Expiration Monitoring** - Certificates can expire unexpectedly
6. **Trust Issues** - All hosts must trust cert-manager with their private keys
7. **Single Point of Failure** - Cert-manager compromise = entire cluster compromise

### Security Violations (2026 Standards)
- ❌ Private keys transmitted over network (even via Ansible)
- ❌ No hardware security module (HSM) support
- ❌ No automatic rotation
- ❌ No certificate transparency logging
- ❌ Long-lived certificates (175200h = ~20 years default!)
- ❌ No monitoring/alerting
- ❌ Manual distribution process

## Proposed Solutions

### Phase 1: CSR-Based Model (Industry Standard) ⭐ RECOMMENDED
**Timeline**: 2-3 weeks
**Complexity**: Medium
**Security Impact**: HIGH

#### Concept
Each host generates its own private key locally, creates a Certificate Signing Request (CSR), sends CSR to CA, receives signed certificate back.

#### Benefits
- ✅ Private keys NEVER leave the host
- ✅ Industry standard approach (used by Kubernetes, OpenSSL, etc.)
- ✅ Minimal external dependencies
- ✅ Compatible with existing ansible workflow
- ✅ Can be done incrementally

#### Implementation Tasks

**1.1 Simplify Certificate Naming**
- [ ] Use consistent pattern: `${etcd_name}-${profile}.{key,crt,ca}`
  - Example: `etcd-k8s-1-peer.key`, `etcd-k8s-1-peer.crt`, `etcd-k8s-1-peer.ca`
- [ ] Remove hostname from cert filenames
- [ ] Store all certs in `${etcd_cert_dir}/` (no subdirectories per host)
- [ ] Update all references in templates and tasks

**1.2 Implement CSR Workflow**
```
┌─────────────────┐
│  Each ETCD Host │
└────────┬────────┘
         │ 1. Generate private key locally
         │ 2. Create CSR with cfssl
         ├──────────────────────────────────►┌──────────────┐
         │    Send CSR to CA                  │              │
         │                                    │ Cert Manager │
         │ 4. Receive signed cert            │  (CA Host)   │
         │◄───────────────────────────────────┤              │
         │    3. CA signs CSR                 └──────────────┘
         │
         ▼ 5. Install signed cert + CA cert
```

Tasks:
- [ ] Create new role: `etcd3/certs/generate-local`
  - Generates private key on target host
  - Creates CSR using cfssl
  - Returns CSR content as fact
- [ ] Create new role: `etcd3/certs/sign-csr`
  - Receives CSR from hosts
  - Signs CSR with CA
  - Returns signed certificate
- [ ] Update `etcd3/certs/fetch` to orchestrate workflow
- [ ] Remove tarball distribution logic
- [ ] Update cert paths to use new naming scheme

**1.3 Reduce Certificate Lifetime**
- [ ] Change default `cert_expiry` from 175200h (20 years) to 2160h (90 days)
- [ ] Add `cert_expiry_peer`, `cert_expiry_client`, `cert_expiry_server` for granular control
- [ ] Document why short-lived certificates are more secure

**1.4 Implement Automatic Rotation**
- [ ] Create playbook `playbooks/etcd-rotate-certs.yaml`
- [ ] Add cron job option to run rotation automatically
- [ ] Check certificate expiration before rotation
- [ ] Only rotate certs expiring within threshold (e.g., 30 days)
- [ ] Zero-downtime rotation (rotate one node at a time)

**1.5 Add Certificate Monitoring**
- [ ] Create task to check cert expiration dates
- [ ] Export metrics for Prometheus (optional)
- [ ] Create playbook `playbooks/etcd-check-certs.yaml`
- [ ] Add warning when certs expire within 30 days
- [ ] Email/webhook alerts on expiration (optional)

**1.6 Security Enhancements**
- [ ] Set restrictive permissions on private keys (0400, root only)
- [ ] Implement certificate pinning in client configs
- [ ] Add certificate transparency logging (optional)
- [ ] Support for hardware security modules (HSM) for CA key (optional)
- [ ] Add audit logging for all cert operations

---

### Phase 2: Automated Certificate Management ⭐ FUTURE
**Timeline**: 4-6 weeks
**Complexity**: High
**Security Impact**: VERY HIGH

#### Option A: Smallstep/step-ca Integration
Use modern step-ca for automated certificate lifecycle management.

**Benefits:**
- ✅ Automated rotation via ACME protocol
- ✅ Short-lived certificates by default (24 hours possible)
- ✅ Built-in monitoring and observability
- ✅ Support for multiple authentication methods
- ✅ Certificate templates
- ✅ Active development and support

**Tasks:**
- [ ] Add step-ca deployment role
- [ ] Configure step-ca with etcd CA
- [ ] Update etcd hosts to use step-cli for cert renewal
- [ ] Implement automated renewal via systemd timer
- [ ] Migration playbook from current certs to step-ca
- [ ] Documentation and examples

**Reference:** https://smallstep.com/docs/step-ca

#### Option B: HashiCorp Vault PKI Engine
Use Vault's PKI secret engine for dynamic certificate generation.

**Benefits:**
- ✅ Enterprise-grade secret management
- ✅ Dynamic certificate generation
- ✅ Automatic rotation
- ✅ Audit logging built-in
- ✅ Integration with existing Vault deployments
- ✅ Policy-based access control

**Tasks:**
- [ ] Add Vault PKI backend configuration
- [ ] Create role for etcd certificate issuance
- [ ] Update etcd hosts to fetch certs from Vault
- [ ] Implement renewal via Vault agent
- [ ] Migration playbook
- [ ] Documentation

**Reference:** https://www.vaultproject.io/docs/secrets/pki

---

### Phase 3: Client Certificate On-Demand Generation
**Timeline**: 1-2 weeks
**Complexity**: Medium

#### Concept
Allow clients to generate certificates on-demand when they have authenticated access to an etcd node.

**Use Cases:**
- New client needs to connect to etcd
- Client certificate expired
- Security incident requires cert rotation
- Temporary access for debugging

#### Implementation

**3.1 Create Client Certificate Request Tool**
- [ ] Create script `bin/etcd-request-client-cert.sh`
  ```bash
  #!/bin/bash
  # Usage: etcd-request-client-cert.sh <client-name> <output-dir>
  # Runs on etcd node, requires root access
  # Generates client certificate and returns to caller
  ```
- [ ] Script generates CSR locally
- [ ] Signs with etcd client CA
- [ ] Returns certificate bundle
- [ ] Logs all certificate issuance to audit log

**3.2 API-Based Certificate Issuance (Advanced)**
- [ ] Create simple REST API on etcd nodes (optional)
- [ ] Authenticate via mutual TLS or token
- [ ] Rate limiting to prevent abuse
- [ ] Automatic expiration (e.g., 7 days for debug certs)
- [ ] Integration with existing authentication systems (LDAP, OAuth, etc.)

**3.3 Security Controls**
- [ ] Only etcd cluster members can issue client certs
- [ ] Require authentication (sudo, SSH key, mutual TLS)
- [ ] Rate limiting (max certs per client per day)
- [ ] Audit logging of all issued certificates
- [ ] Certificate revocation list (CRL) support
- [ ] Short-lived certificates for temporary access

---

## Implementation Priority

### Must Have (Phase 1 - Do First)
1. ✅ CSR-based certificate generation
2. ✅ Simplified naming scheme
3. ✅ Configurable certificate lifetime (default 2 years for manual planning)
4. ✅ Certificate expiration monitoring
5. ✅ Basic rotation playbook

### Should Have (Phase 1 - Do Soon)
6. ✅ Automated rotation cron job
7. ✅ Zero-downtime rotation
8. ✅ Certificate pinning
9. ✅ Audit logging

### Nice to Have (Phase 2/3 - Future)
10. 🚧 step-ca integration (IN PROGRESS)
11. ⏳ On-demand client cert generation
12. ⏳ HSM support
13. ⏳ Certificate transparency logging
14. ⏳ Prometheus metrics

---

## Detailed Implementation Plan: Phase 1

### Step 1: Simplify Certificate Naming (Week 1)

**Goal:** Make cert filenames consistent and predictable

**Current:**
```
/etc/etcd/ssl/node1.example.com/node1.example.com-peer.pem
/etc/etcd/ssl/node1.example.com/node1.example.com-peer-key.pem
/etc/etcd/ssl/node1.example.com/peer-ca.pem
```

**Proposed:**
```
/etc/etcd/ssl/etcd-k8s-1-peer.crt
/etc/etcd/ssl/etcd-k8s-1-peer.key
/etc/etcd/ssl/etcd-k8s-1-client.crt
/etc/etcd/ssl/etcd-k8s-1-client.key
/etc/etcd/ssl/peer-ca.crt
/etc/etcd/ssl/client-ca.crt
```

**Variables to update:**
```yaml
etcd_cert_paths:
  server:
    cert: "{{ etcd_cert_dir }}/{{ etcd_name }}-server.crt"
    key: "{{ etcd_cert_dir }}/{{ etcd_name }}-server.key"
    ca: "{{ etcd_cert_dir }}/client-ca.crt"
  client:
    cert: "{{ etcd_cert_dir }}/{{ etcd_name }}-client.crt"
    key: "{{ etcd_cert_dir }}/{{ etcd_name }}-client.key"
    ca: "{{ etcd_cert_dir }}/client-ca.crt"
  peer:
    cert: "{{ etcd_cert_dir }}/{{ etcd_name }}-peer.crt"
    key: "{{ etcd_cert_dir }}/{{ etcd_name }}-peer.key"
    ca: "{{ etcd_cert_dir }}/peer-ca.crt"
```

**Files to update:**
- `roles/etcd3/defaults/main.yaml` - Update `etcd_cert_paths`
- `roles/etcd3/certs/generate/tasks/0020_etcd-certs.yaml` - Update file paths
- All template files using cert paths

### Step 2: Implement CSR Workflow (Week 2)

**Create new role structure:**
```
roles/etcd3/certs/local/
├── tasks/
│   ├── main.yml              # Orchestration
│   ├── generate-key.yml      # Generate private key locally
│   ├── create-csr.yml        # Create CSR
│   └── install-cert.yml      # Install signed cert
└── templates/
    └── csr-config.json       # CSR configuration
```

**Workflow:**
```yaml
# On each etcd/client host:
1. Generate private key locally
   openssl genrsa -out etcd-k8s-1-peer.key 2048

2. Create CSR
   cfssl genkey csr-config.json | cfssljson -bare etcd-k8s-1-peer

3. Send CSR to cert-manager (via ansible fact)
   set_fact:
     etcd_csr_content: "{{ lookup('file', 'etcd-k8s-1-peer.csr') }}"

4. Cert-manager signs CSR
   cfssl sign -ca=peer-ca.pem -ca-key=peer-ca-key.pem etcd-k8s-1-peer.csr

5. Return signed cert to host
   copy:
     content: "{{ etcd_signed_cert }}"
     dest: "{{ etcd_cert_dir }}/etcd-k8s-1-peer.crt"
```

### Step 3: Reduce Certificate Lifetime (Week 2)

**Update defaults:**
```yaml
# From 20 years to 90 days
cert_expiry: 2160h  # 90 days

# Granular control
cert_expiry_ca: 87600h      # 10 years (CA should be long-lived)
cert_expiry_peer: 2160h     # 90 days
cert_expiry_client: 2160h   # 90 days
cert_expiry_server: 2160h   # 90 days
```

### Step 4: Certificate Monitoring (Week 3)

**Create monitoring playbook:**
```yaml
# playbooks/etcd-check-certs.yaml
- hosts: etcd:etcd-clients
  tasks:
    - name: Check certificate expiration
      command: |
        openssl x509 -in {{ item }} -noout -enddate
      register: cert_expiry
      loop:
        - "{{ etcd_cert_paths.peer.cert }}"
        - "{{ etcd_cert_paths.client.cert }}"
      
    - name: Calculate days until expiration
      set_fact:
        cert_days_remaining: "{{ ... }}"
    
    - name: Warn if expiring soon
      debug:
        msg: "WARNING: Certificate expires in {{ cert_days_remaining }} days!"
      when: cert_days_remaining | int < 30
```

### Step 5: Automated Rotation (Week 3)

**Create rotation playbook:**
```yaml
# playbooks/etcd-rotate-certs.yaml
- hosts: etcd
  serial: 1  # One node at a time
  tasks:
    - name: Check if rotation needed
      # Only rotate if expiring within 30 days
      
    - name: Generate new CSR
      # Use new CSR workflow
      
    - name: Get signed certificate
      # Sign CSR
      
    - name: Install new certificate
      # Replace old cert
      
    - name: Reload etcd
      systemd:
        name: "{{ etcd_name }}"
        state: reloaded
      
    - name: Wait for health
      # Verify cluster is healthy
```

---

## Migration Plan

### Backward Compatibility
- [ ] Support both old and new cert paths during transition
- [ ] Create migration playbook to rename existing certs
- [ ] Document migration process
- [ ] Add rollback procedure

### Testing Plan
- [ ] Test CSR generation on all supported OS
- [ ] Test certificate rotation without downtime
- [ ] Test client certificate distribution
- [ ] Load testing during rotation
- [ ] Security audit of new implementation

---

## Documentation Requirements

### User Documentation
- [ ] Certificate architecture diagram
- [ ] Quick start guide for new deployments
- [ ] Migration guide for existing deployments
- [ ] Troubleshooting guide
- [ ] Security best practices
- [ ] FAQ

### Developer Documentation
- [ ] CSR workflow documentation
- [ ] Certificate naming conventions
- [ ] Testing procedures
- [ ] Code architecture
- [ ] API documentation (if applicable)

---

## Success Metrics

### Security Metrics
- Private keys never transmitted over network
- Certificate lifetime reduced to 90 days
- Automated rotation working for 100% of clusters
- Zero security incidents related to certificate management

### Operational Metrics
- Certificate rotation time < 5 minutes per node
- Zero downtime during rotation
- 100% of certificates monitored for expiration
- Mean time to issue new client cert < 2 minutes

### User Experience Metrics
- Simpler certificate file structure
- Reduced support tickets for cert issues
- Clear documentation and examples
- Positive user feedback

---

## Security Considerations

### Threat Model
**Threats:**
1. Compromised cert-manager host
2. Man-in-the-middle attacks during cert distribution
3. Private key theft
4. Certificate expiration causing outages
5. Unauthorized certificate issuance

**Mitigations:**
1. Use CSR model (private keys stay on host)
2. Use Ansible's SSH encryption for CSR transmission
3. Strict file permissions (0400 for keys)
4. Automated monitoring and rotation
5. Audit logging and rate limiting

### Compliance
- [ ] Document compliance with industry standards (PCI-DSS, SOC2, etc.)
- [ ] Implement audit logging for all cert operations
- [ ] Ensure certificate storage meets encryption requirements
- [ ] Support for FIPS 140-2 compliant crypto (optional)

---

## Open Questions

1. **HSM Support**: Should we support hardware security modules for CA key storage?
   - Decision: Optional for Phase 2, document how to integrate

2. **Certificate Revocation**: How to handle compromised certificates?
   - Decision: Implement CRL support in Phase 1, OCSP in Phase 2

3. **Multi-Cluster**: How to manage certs across multiple etcd clusters?
   - Decision: Each cluster has independent CA, document federation

4. **Backup/Restore**: How to backup/restore CA keys?
   - Decision: Add to backup playbook, encrypt CA keys at rest

5. **Key Algorithm**: Stay with RSA 2048 or move to ECDSA?
   - Decision: Support both, default to RSA 2048 for compatibility

---

## References

- [Kubernetes PKI Certificate Best Practices](https://kubernetes.io/docs/setup/best-practices/certificates/)
- [NIST Guidelines for Digital Signatures (SP 800-89)](https://csrc.nist.gov/publications/detail/sp/800-89/final)
- [Let's Encrypt Certificate Lifecycle](https://letsencrypt.org/docs/certificate-lifecycle/)
- [Smallstep Security Best Practices](https://smallstep.com/docs/step-ca/certificate-authority-server-production)
- [HashiCorp Vault PKI Documentation](https://www.vaultproject.io/docs/secrets/pki)
- [etcd Security Model](https://etcd.io/docs/latest/op-guide/security/)
- [CloudFlare CFSSL Documentation](https://github.com/cloudflare/cfssl)

---

## Summary

**Recommended Approach:**
1. Start with Phase 1 (CSR-based model)
2. Implement simplified naming immediately
3. Reduce cert lifetime to 90 days
4. Add monitoring and automated rotation
5. Evaluate Phase 2 (step-ca or Vault) after 6 months

**Key Benefits:**
- ✅ Dramatically improved security (private keys never leave hosts)
- ✅ Industry standard approach (CSR model)
- ✅ Simplified operations (consistent naming, automated rotation)
- ✅ Better monitoring and visibility
- ✅ Incremental migration path
- ✅ No external dependencies (Phase 1)

**Estimated Effort:**
- Phase 1: 3-4 weeks (1 developer)
- Migration: 1-2 weeks (testing and rollout)
- Total: 4-6 weeks for production-ready implementation
