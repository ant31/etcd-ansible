# Ansible Module Replacement TODO

This document tracks places where `command` or `shell` modules should be replaced with native Ansible builtins.

## Priority 1: Easy Wins (Simple Replacements)

### roles/etcd3/operations/tasks/verify-backup-cron.yml

**Line 6-10: Replace `command: date` with `ansible_date_time` fact**
```yaml
# CURRENT:
- name: Get current date/time
  command: date '+%Y-%m-%d %H:%M:%S %Z'
  register: current_time
  changed_when: false

# SHOULD BE:
- name: Set current date/time from facts
  set_fact:
    current_time:
      stdout: "{{ ansible_date_time.date }} {{ ansible_date_time.time }} {{ ansible_date_time.tz }}"
```

**Line 12-16: Replace `command: id` with `getent` module**
```yaml
# CURRENT:
- name: Check if etcd user exists
  command: id {{ etcd_user.name }}
  register: etcd_user_check
  changed_when: false
  failed_when: false

# SHOULD BE:
- name: Check if etcd user exists
  getent:
    database: passwd
    key: "{{ etcd_user.name }}"
  register: etcd_user_check
  failed_when: false
```

### roles/etcd3/operations/tasks/health-stepca.yml

**Line 8-11: Replace `command: systemctl is-active` with `service_facts`**
```yaml
# CURRENT:
- name: Check step-ca service status
  command: systemctl is-active step-ca
  register: step_ca_active
  changed_when: false
  failed_when: false

# SHOULD BE:
- name: Gather service facts
  service_facts:

- name: Set step-ca active status
  set_fact:
    step_ca_active:
      stdout: "{{ 'active' if ansible_facts.services['step-ca.service'].state == 'running' else 'inactive' }}"
```

### roles/etcd3/cluster/install/tasks/0010_cluster.yaml

**Line 8-11: Replace `shell: df` with `ansible_mounts` fact**
```yaml
# CURRENT:
- name: Check available disk space
  shell: df -BG {{ etcd_home }} | tail -1 | awk '{print $4}' | sed 's/G//'
  register: disk_space_gb
  changed_when: false

# SHOULD BE:
- name: Get mount point for etcd_home
  set_fact:
    etcd_mount: "{{ ansible_mounts | selectattr('mount', 'equalto', etcd_home) | first | default(ansible_mounts | selectattr('mount', 'in', etcd_home) | sort(attribute='mount', reverse=true) | first) }}"

- name: Calculate available disk space in GB
  set_fact:
    disk_space_gb:
      stdout: "{{ ((etcd_mount.size_available / 1024 / 1024 / 1024) | int) }}"
```

**Line 46-49: Replace `shell` with `command` (simpler, no shell needed)**
```yaml
# CURRENT:
- name: Check current etcd version (if exists)
  shell: "{{ bin_dir }}/etcd --version | head -1 | awk '{print $3}'"
  register: current_etcd_version

# SHOULD BE:
- name: Check current etcd version (if exists)
  command: "{{ bin_dir }}/etcd --version"
  register: current_etcd_version_raw
  changed_when: false
  failed_when: false

- name: Extract version number
  set_fact:
    current_etcd_version:
      stdout: "{{ current_etcd_version_raw.stdout_lines[0].split()[2] if current_etcd_version_raw.rc == 0 else '' }}"
  when: current_etcd_version_raw.rc == 0
```

### roles/etcd3/certs/operations/tasks/renew.yml

**Line 1-5: Replace `command: systemctl` with `service_facts` or `systemd` module**
```yaml
# CURRENT:
- name: Check if step-ca is running on cert-managers
  command: systemctl is-active step-ca
  register: step_ca_status
  changed_when: false
  failed_when: false
  delegate_to: "{{ groups[etcd_certmanagers_group][0] }}"
  run_once: true

# SHOULD BE:
- name: Gather service facts on cert-manager
  service_facts:
  delegate_to: "{{ groups[etcd_certmanagers_group][0] }}"
  run_once: true

- name: Set step-ca running status
  set_fact:
    step_ca_status:
      stdout: "{{ 'active' if ansible_facts.services['step-ca.service'].state | default('') == 'running' else 'inactive' }}"
  delegate_to: "{{ groups[etcd_certmanagers_group][0] }}"
  run_once: true
```

### roles/etcd3/certs/operations/tasks/rotate.yml

**Similar to renew.yml - replace `command: systemctl` with `service_facts`**

### roles/etcd3/certs/operations/tasks/regenerate-nodes.yml

**Line 30-34: Replace `shell: rm -f` with `file` module loop**
```yaml
# CURRENT:
- name: Remove certificate renewal services and timers
  shell: |
    rm -f /etc/systemd/system/step-renew-*.service
    rm -f /etc/systemd/system/step-renew-*.timer
    systemctl daemon-reload

# SHOULD BE:
- name: Find certificate renewal services and timers
  find:
    paths: /etc/systemd/system
    patterns: "step-renew-*.service,step-renew-*.timer"
  register: renewal_files

- name: Remove certificate renewal services and timers
  file:
    path: "{{ item.path }}"
    state: absent
  loop: "{{ renewal_files.files }}"
  loop_control:
    label: "{{ item.path }}"

- name: Reload systemd daemon
  systemd:
    daemon_reload: yes
```

### roles/etcd3/certs/operations/tasks/regenerate.yml

**Line 7-17: Replace `shell` with `systemd` module + `find` + `file`**
```yaml
# CURRENT:
- name: Kill any running step-ca processes and clean temp files (force cleanup)
  shell: |
    pkill -9 step-ca || true
    sleep 2
    rm -rf /tmp/step-ca-* 2>/dev/null || true
    rm -rf /var/tmp/step-ca-* 2>/dev/null || true

# SHOULD BE:
- name: Forcefully stop step-ca processes
  command: pkill -9 step-ca
  failed_when: false

- name: Wait for processes to terminate
  pause:
    seconds: 2

- name: Find step-ca temporary files
  find:
    paths:
      - /tmp
      - /var/tmp
    patterns: "step-ca-*"
  register: step_ca_temp_files

- name: Remove step-ca temporary files
  file:
    path: "{{ item.path }}"
    state: absent
  loop: "{{ step_ca_temp_files.files }}"
  loop_control:
    label: "{{ item.path }}"
```

**Line 43-56: Replace `shell` with `find` + `file` modules**
```yaml
# CURRENT:
- name: Remove step CLI bootstrap cache and temporary files
  shell: |
    rm -f {{ etcd_cert_dir }}/root_ca.crt
    rm -rf {{ etcd_cert_dir }}/.step
    rm -rf /root/.step
    rm -rf /home/{{ etcd_user.name }}/.step
    find /root -name '*.csr' -mtime -1 -delete 2>/dev/null || true
    find /tmp -name 'step-*' -mtime -1 -delete 2>/dev/null || true
    rm -rf /root/.smallstep 2>/dev/null || true

# SHOULD BE:
- name: Remove step CLI bootstrap cache directories
  file:
    path: "{{ item }}"
    state: absent
  loop:
    - "{{ etcd_cert_dir }}/root_ca.crt"
    - "{{ etcd_cert_dir }}/.step"
    - /root/.step
    - "/home/{{ etcd_user.name }}/.step"
    - /root/.smallstep

- name: Find recent CSR files in root
  find:
    paths: /root
    patterns: "*.csr"
    age: -1d
  register: csr_files

- name: Remove recent CSR files
  file:
    path: "{{ item.path }}"
    state: absent
  loop: "{{ csr_files.files }}"

- name: Find step temporary files
  find:
    paths: /tmp
    patterns: "step-*"
    age: -1d
  register: step_temp_files

- name: Remove step temporary files
  file:
    path: "{{ item.path }}"
    state: absent
  loop: "{{ step_temp_files.files }}"
```

**Line 64-68: Replace `shell: rm -f` with `find` + `file`**
```yaml
# CURRENT:
- name: Remove certificate renewal services and timers
  shell: |
    rm -f /etc/systemd/system/step-renew-*.service
    rm -f /etc/systemd/system/step-renew-*.timer

# SHOULD BE: (same as regenerate-nodes.yml suggestion)
```

### roles/etcd3/restore/tasks/restore-ca-from-backup-direct.yml

**Line 3-13: Replace `shell` with proper `systemd` module**
```yaml
# CURRENT:
- name: Kill any running step-ca processes (force cleanup on backup cert-managers when force replication OR force cleanup)
  shell: |
    pkill -9 step-ca || true
    sleep 2
    rm -rf /tmp/step-ca-* 2>/dev/null || true
    rm -rf /var/tmp/step-ca-* 2>/dev/null || true

# SHOULD BE: (similar to regenerate.yml suggestion above)
```

**Line 33-46: Replace `find` command with `ansible.builtin.find` module**
```yaml
# CURRENT:
- name: Clean step-ca log files (prevents key mismatch errors on backup cert-managers)
  find:
    paths: /var/log
    patterns: "step-ca*.log"
    file_type: file
  register: step_ca_log_files

# This is already using the module! Good!
```

### roles/etcd3/cleanup/tasks/clean-data.yml

**Line 18-20: Replace `shell: rm -rf` with `find` + `file` modules**
```yaml
# CURRENT:
- name: Remove etcd data directories
  shell: rm -rf /var/lib/etcd/etcd-*

# SHOULD BE:
- name: Find etcd data directories
  find:
    paths: /var/lib/etcd
    patterns: "etcd-*"
    file_type: directory
  register: etcd_data_dirs

- name: Remove etcd data directories
  file:
    path: "{{ item.path }}"
    state: absent
  loop: "{{ etcd_data_dirs.files }}"
  loop_control:
    label: "{{ item.path }}"
```

### roles/etcd3/cleanup/tasks/clean-backups.yml

**Line 18-22: Already uses `shell` with `find` - could use `find` + `file` modules**
```yaml
# CURRENT:
- name: Clean old local backups
  shell: |
    find /var/lib/etcd/backups -type f -mtime +30 -delete
    find /var/lib/etcd/backups -type d -empty -delete

# SHOULD BE:
- name: Find old backup files
  find:
    paths: /var/lib/etcd/backups
    file_type: file
    age: 30d
    recurse: yes
  register: old_backup_files

- name: Remove old backup files
  file:
    path: "{{ item.path }}"
    state: absent
  loop: "{{ old_backup_files.files }}"
  loop_control:
    label: "{{ item.path }}"

- name: Find empty backup directories
  find:
    paths: /var/lib/etcd/backups
    file_type: directory
    recurse: yes
  register: all_backup_dirs

- name: Remove empty directories
  file:
    path: "{{ item.path }}"
    state: absent
  loop: "{{ all_backup_dirs.files }}"
  when: item.path | dirname | length > 0  # Don't delete root
  failed_when: false  # OK if directory not empty
  loop_control:
    label: "{{ item.path }}"
```

### roles/etcd3/certs/smallstep/tasks/install-ca.yml

**Line 88-92: Replace `command: /usr/bin/python3` with `script` module**
```yaml
# CURRENT:
- name: Configure step-ca certificate durations
  command: /usr/bin/python3 /tmp/configure_step_ca_durations.py
  register: configure_durations_result
  when: not step_ca_config_stat.stat.exists

# SHOULD BE:
- name: Configure step-ca certificate durations
  script: /tmp/configure_step_ca_durations.py
  register: configure_durations_result
  when: not step_ca_config_stat.stat.exists
  args:
    executable: /usr/bin/python3
```

### roles/etcd3/restore/tasks/restore-ca-from-s3.yml

**Line 69-73: Replace `shell` with `find` + `file`**
```yaml
# CURRENT:
- name: Set CA private key permissions (root only, 0400)
  shell: |
    find /etc/step-ca/secrets -type f -name "*_key" -exec chmod 0400 {} \;
    find /etc/step-ca/secrets -type f -name "*_key" -exec chown root:root {} \;

# SHOULD BE:
- name: Find CA private key files
  find:
    paths: /etc/step-ca/secrets
    patterns: "*_key"
    file_type: file
    recurse: yes
  register: ca_key_files

- name: Set CA private key permissions (root only, 0400)
  file:
    path: "{{ item.path }}"
    owner: root
    group: root
    mode: '0400'
  loop: "{{ ca_key_files.files }}"
  loop_control:
    label: "{{ item.path }}"
```

### roles/etcd3/restore/tasks/restore-ca-from-backup-direct.yml

**Line 177-181: Same as above - replace `shell` with `find` + `file`**

### roles/etcd3/certs/smallstep/tasks/install-ca.yml

**Line 126-137: Replace `shell` with `find` + `file`**
```yaml
# CURRENT (around line 126):
- name: Fix CA secrets files permissions (private keys - root only)
  file:
    path: "{{ item }}"
    owner: root
    group: root
    mode: 0400
  loop:
    - "{{ step_ca_secrets }}/root_ca_key"
    - "{{ step_ca_secrets }}/intermediate_ca_key"
    - "{{ step_ca_secrets }}/password"
  failed_when: false

# This is already good! But could be improved with find for dynamic discovery:
- name: Find all CA secret files
  find:
    paths: "{{ step_ca_secrets }}"
    file_type: file
  register: ca_secret_files

- name: Fix CA secrets files permissions (private keys - root only)
  file:
    path: "{{ item.path }}"
    owner: root
    group: root
    mode: '0400'
  loop: "{{ ca_secret_files.files }}"
```

## Priority 2: Complex Replacements (Require More Work)

### roles/etcd3/operations/tasks/status.yml

**Consider using `json_query` filter instead of shell piping**
```yaml
# CURRENT:
- name: Get cluster status
  shell: |
    {{ bin_dir }}/etcdctl \
      --endpoints=$(cat /etc/etcd/etcd-*-conf.yaml | grep advertise-client-urls | cut -d' ' -f2 | sed 's/,/,https:\/\//g') \
      ...

# SHOULD BE:
- name: Read etcd config file
  slurp:
    src: "/etc/etcd/etcd-{{ etcd_cluster_name }}-conf.yaml"
  register: etcd_config_raw

- name: Parse advertise-client-urls from config
  set_fact:
    etcd_endpoints: "{{ (etcd_config_raw.content | b64decode | from_yaml)['advertise-client-urls'] }}"

- name: Get cluster status
  command: >
    {{ bin_dir }}/etcdctl
    --endpoints={{ etcd_endpoints }}
    --cert=/etc/etcd/ssl/etcd-*-client.crt
    ...
```

### roles/etcd3/certs/operations/tasks/rotate.yml

**Line 28-33: Replace `shell` for-loop with `find` + `systemd`**
```yaml
# CURRENT:
- name: Force certificate rotation (start all renewal services)
  shell: |
    for timer in /etc/systemd/system/step-renew-*.timer; do
      systemctl start $(basename $timer .timer).service
    done

# SHOULD BE:
- name: Find renewal timer files
  find:
    paths: /etc/systemd/system
    patterns: "step-renew-*.timer"
  register: renewal_timers

- name: Extract service names from timer files
  set_fact:
    renewal_services: "{{ renewal_timers.files | map(attribute='path') | map('basename') | map('regex_replace', '\\.timer$', '.service') | list }}"

- name: Force certificate rotation (start all renewal services)
  systemd:
    name: "{{ item }}"
    state: started
  loop: "{{ renewal_services }}"
```

## Priority 3: Keep As-Is (Legitimate Use of shell/command)

### Legitimate External Commands (No Ansible Module)

These are **correct** to use `command` or `shell`:

1. **etcdctl commands** - No Ansible module exists for etcdctl
   - `roles/etcd3/operations/tasks/health.yml`
   - `roles/etcd3/operations/tasks/members.yml`
   - `roles/etcd3/operations/tasks/status.yml`
   - `roles/etcd3/operations/tasks/compact.yml`
   - `roles/etcd3/operations/tasks/defrag.yml`
   - `roles/etcd3/cluster/install/tasks/0010_cluster.yaml`

2. **step / step-ca commands** - No Ansible module exists
   - `roles/etcd3/certs/smallstep/tasks/configure-renewal.yml`
   - `roles/etcd3/certs/smallstep/tasks/install-ca.yml`
   - `roles/etcd3/certs/smallstep/tasks/install-client.yml`
   - `roles/etcd3/operations/tasks/health-certs.yml`
   - `roles/etcd3/operations/tasks/health-stepca.yml`

3. **AWS CLI commands** - Could use `amazon.aws` collection, but `command` is simpler for one-off operations
   - `roles/etcd3/certs/replicate/tasks/main.yml`
   - `roles/etcd3/restore/tasks/restore-ca-from-s3.yml`
   - `roles/etcd3/restore/tasks/restore-etcd.yml`
   - `roles/etcd3/restore/tasks/restore-ca-from-backup-direct.yml`

4. **journalctl commands** - No Ansible module for viewing logs
   - `roles/etcd3/operations/tasks/logs.yml`
   - `roles/etcd3/operations/tasks/logs-follow.yml`
   - `roles/etcd3/cleanup/tasks/clean-logs.yml`

5. **Complex shell operations** - Would be harder to maintain as pure Ansible
   - Cron schedule parsing in `roles/etcd3/operations/tasks/verify-backup-cron.yml`
   - JSON/JQ parsing where `json_query` filter would be too complex

6. **etcdutl commands** - No Ansible module exists
   - `roles/etcd3/restore/tasks/restore-etcd.yml`

### Shell Features Required (Legitimate)

These use shell-specific features that can't be done with `command`:

1. **Process substitution (`<(...)`)** - Required for password input
   - `roles/etcd3/certs/smallstep/tasks/configure-renewal.yml`

2. **Pipes and complex parsing** - More maintainable as shell script
   - Various etcdctl outputs with `awk`, `grep`, `sed`

## Summary Statistics

- **Priority 1 (Easy)**: ~15 replacements
- **Priority 2 (Complex)**: ~5 replacements  
- **Keep As-Is (Legitimate)**: ~50+ occurrences

## Implementation Notes

1. **service_facts** module gathers ALL services, might be slow on systems with many services. Consider caching.
2. **find** module is more portable than shell `find` with `-delete`
3. **json_query** filter (from community.general) can replace many jq operations
4. Test replacements in check mode first: `--check --diff`

## Benefits of Using Builtins

1. ✅ **Idempotent** - Ansible tracks state properly
2. ✅ **Cross-platform** - Works on more systems
3. ✅ **Changed detection** - Better reporting
4. ✅ **Dry-run support** - `--check` mode works correctly
5. ✅ **Error handling** - More granular error messages
6. ✅ **Security** - No shell injection risks

## When to Keep shell/command

1. ❌ External tools with no Ansible module (etcdctl, step, aws)
2. ❌ Complex parsing that would be unreadable in Jinja2
3. ❌ Shell-specific features (pipes, process substitution)
4. ❌ One-liners that are clearer as shell than as 5 Ansible tasks

## Important Variables for CA Operations

### etcd_force_ca_replication (default: true)
- **Used during**: Normal deployment when multiple cert-managers configured
- **Affects**: Backup cert-managers only (cert-managers[1:])
- **Purpose**: Replace CA on backup nodes during replication
- **Triggers**: Cleanup of badger DB, templates, cache (prevents key mismatch)
- **Confirmation**: No prompt (automatic during deployment)

### etcd_force_ca_replacement (default: false)
- **Used during**: DISASTER RECOVERY ONLY
- **Affects**: ALL cert-managers (including primary)
- **Purpose**: Complete CA rebuild when CA compromised on all nodes
- **Triggers**: Same cleanup as etcd_force_ca_replication
- **Confirmation**: REQUIRES explicit confirmation ('yes-force-replace-all')
- **Called during deploy?**: Only if explicitly set to true via -e flag

### step_ca_force_cleanup (default: false)
- **Used during**: Manual CA restoration or troubleshooting
- **Affects**: Backup cert-managers only (cert-managers[1:])
- **Purpose**: Clean badger DB and cache without replacing CA
- **Triggers**: Cleanup only (no CA deletion unless combined with force_ca_replication)
- **Confirmation**: No prompt (tool for fixing key mismatch errors)

### Normal Deployment Flow (etcd_action=deploy)
1. Primary cert-manager: Creates CA → Backs up to S3
2. Backup cert-managers: Restores CA from S3
3. By default uses: `etcd_force_ca_replication=true` (automatic cleanup)
4. Does NOT use: `etcd_force_ca_replacement=false` (stays false)
5. Result: Primary keeps CA, backups get replicated CA
