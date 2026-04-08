# Troubleshooting Guide

## Common Issues and Solutions

### SSH Access Issues

#### Problem: Permission Denied

```
Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password).
```

**Solution**:
```bash
# Copy SSH key to target
ssh-copy-id root@<hostname>

# Or use password (for initial setup)
ssh -o PreferredAuthentications=password root@<hostname>
```

#### Problem: Connection Refused

```
ssh: connect to host <hostname> port 22: Connection refused
```

**Solution**:
```bash
# Check if host is reachable
ping <hostname>

# Check if sshd is running (requires console access)
systemctl status sshd

# Check firewall
firewall-cmd --list-all
```

#### Problem: Host Key Changed

```
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

**Solution**:
```bash
# Remove old key
ssh-keygen -R <hostname>

# Reconnect
ssh root@<hostname>
```

---

### Nginx Issues

#### Problem: Nginx Won't Start

```
nginx: [emerg] bind() to 0.0.0.0:80 failed (98: Address already in use)
```

**Solution**:
```bash
# Find what's using port 80
ss -tlnp | grep :80

# Kill conflicting process or change nginx port
kill <pid>
systemctl start nginx
```

#### Problem: Config Test Fails

```
nginx: [emerg] unknown directive "..."
```

**Solution**:
```bash
# Check nginx version
nginx -v

# Verify module is loaded
nginx -V 2>&1 | grep <module>

# Fix syntax and test again
nginx -t
```

#### Problem: Permission Denied on Files

```
open() "/path/to/file" failed (13: Permission denied)
```

**Solution**:
```bash
# Check file ownership
ls -la /path/to/file

# Fix permissions
chown -R nginx:nginx /path/to/files
chmod -R 644 /path/to/files

# Check SELinux
getenforce
ls -Z /path/to/file

# If SELinux, fix context
restorecon -Rv /path/to/files
# Or set boolean
setsebool -P httpd_read_user_content 1
```

---

### Benchmark Issues

#### Problem: wrk Not Found

```
wrk: command not found
```

**Solution**:
```bash
# Install wrk
yum install -y wrk

# Or build from source
git clone https://github.com/wg/wrk.git
cd wrk && make
cp wrk /usr/local/bin/
```

#### Problem: Connection Refused to Target

```
unable to connect to test-machine:80
```

**Solution**:
```bash
# Check nginx is running on DUT
ssh root@<DUT> systemctl status nginx

# Check firewall on DUT
ssh root@<DUT> firewall-cmd --list-ports

# Open port 80
ssh root@<DUT> firewall-cmd --add-port=80/tcp --permanent
ssh root@<DUT> firewall-cmd --reload
```

#### Problem: Too Many Open Files

```
socket: Too many open files
```

**Solution**:
```bash
# On benchmark node
ulimit -n 65535

# Make permanent
echo "* soft nofile 65535" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf
```

#### Problem: Benchmark Shows Many Timeouts

```
Socket errors: connect 0, read 0, write 0, timeout 500
```

**Solution**:
```bash
# On DUT, increase connection backlog
sysctl -w net.core.somaxconn=65535
sysctl -w net.ipv4.tcp_max_syn_backlog=65535

# In nginx.conf
# Increase worker_connections
# Reduce keepalive_timeout
```

---

### Performance Issues

#### Problem: High CPU but Low Throughput

**Diagnosis**:
```bash
# Check if CPU is the bottleneck
top -d1

# Check nginx worker count vs cores
ps aux | grep nginx | grep worker | wc -l
nproc
```

**Solution**:
```bash
# Set workers to CPU count
# In nginx.conf:
worker_processes auto;

# Reload
nginx -s reload
```

#### Problem: High I/O Wait

**Diagnosis**:
```bash
# Check I/O stats
iostat -x 1

# Look for high %util and await
```

**Solution**:
```bash
# Enable sendfile in nginx
sendfile on;

# Enable AIO for large files
aio threads;

# Change I/O scheduler
echo "mq-deadline" > /sys/block/sda/queue/scheduler
```

#### Problem: Memory Pressure

**Diagnosis**:
```bash
# Check memory
free -h

# Check for swapping
vmstat 1
```

**Solution**:
```bash
# Reduce nginx buffers
# In nginx.conf:
client_body_buffer_size 16k;

# Or add RAM / swap
```

---

### Kernel Parameter Issues

#### Problem: sysctl Changes Don't Persist

**Solution**:
```bash
# Don't use sysctl -w for permanent changes
# Create file in /etc/sysctl.d/
cat > /etc/sysctl.d/99-nginx.conf << EOF
net.core.somaxconn = 65535
EOF

# Apply
sysctl --system
```

#### Problem: Parameter Ignored

```
sysctl: setting key "net.ipv4.tcp_tw_recycle": Invalid argument
```

**Solution**:
```bash
# Some parameters removed in newer kernels
# tcp_tw_recycle removed in Linux 4.12
# Use tcp_tw_reuse instead
sysctl -w net.ipv4.tcp_tw_reuse=1
```

---

### Rollback Procedures

#### Rollback Nginx Config

```bash
# List backups
ls -la /etc/nginx/nginx.conf.backup.*

# Restore
cp /etc/nginx/nginx.conf.backup.YYYYMMDDHHMMSS /etc/nginx/nginx.conf
nginx -t
nginx -s reload
```

#### Rollback Sysctl Changes

```bash
# Remove custom file
rm /etc/sysctl.d/99-nginx-tuning.conf

# Revert to defaults
sysctl --system
```

#### Rollback Limits

```bash
# Edit /etc/security/limits.conf
# Remove added lines

# Remove systemd override
rm /etc/systemd/system/nginx.service.d/limits.conf
systemctl daemon-reload
systemctl restart nginx
```

#### Full System Rollback

```bash
# If all else fails, restore from known good state
# This requires having taken a snapshot/backup beforehand

# List changes made
cat /root/hackathon-results/tuning_log.json

# Manually reverse each change
```

---

### Diagnostic Commands Cheatsheet

```bash
# System overview
top -bn1 | head -20
free -h
df -h
uptime

# Network
ss -s
ss -tnp | grep nginx
netstat -i

# Nginx
nginx -t
nginx -T  # Show full config
ps aux | grep nginx
cat /var/log/nginx/error.log | tail -50

# Kernel
sysctl -a | grep somaxconn
cat /proc/sys/fs/file-nr

# I/O
iostat -x 1 5
iotop -b -n 5

# SELinux
getenforce
ausearch -m avc -ts recent
```

---

### Getting Help

1. Check nginx error log: `/var/log/nginx/error.log`
2. Check system log: `journalctl -xe`
3. Check dmesg: `dmesg | tail -50`
4. Check audit log (SELinux): `ausearch -m avc`
