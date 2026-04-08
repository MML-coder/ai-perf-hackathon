# Environment Setup

## Systems Overview

### DUT (Device Under Test) - Nginx Server

| Property | Value |
|----------|-------|
| Hostname | `e40-h34-000-r650.rdu2.scalelab.redhat.com` |
| Alias | `test-machine` (in /etc/hosts on benchmark node) |
| OS | RHEL 9.7 |
| Hardware | Dell R650 |
| Role | Nginx web server |
| Credentials | `root` / `100yard-` |

### Benchmark Node - Load Generator

| Property | Value |
|----------|-------|
| Hostname | `e40-h37-000-r650.rdu2.scalelab.redhat.com` |
| OS | RHEL |
| Hardware | Dell R650 |
| Role | wrk benchmark tool |
| Credentials | `root` / `100yard-` |

## SSH Access

### From Local Machine

```bash
# Benchmark node
ssh root@e40-h37-000-r650.rdu2.scalelab.redhat.com

# DUT (Nginx server)
ssh root@e40-h34-000-r650.rdu2.scalelab.redhat.com
```

### Setup SSH Keys (Recommended)

```bash
# Copy your SSH key to both systems
ssh-copy-id root@e40-h37-000-r650.rdu2.scalelab.redhat.com
ssh-copy-id root@e40-h34-000-r650.rdu2.scalelab.redhat.com
```

### From Benchmark Node to DUT

```bash
# The benchmark node has 'test-machine' in /etc/hosts
ssh root@test-machine
```

## DUT System Details

### Nginx Configuration

```bash
# Service status
systemctl status nginx.service

# Main config file
/etc/nginx/nginx.conf

# Check config syntax
nginx -t

# Reload config (no downtime)
nginx -s reload

# Restart service
systemctl restart nginx
```

### Key Files on DUT

| Path | Description |
|------|-------------|
| `/etc/nginx/nginx.conf` | Main Nginx configuration |
| `/etc/nginx/conf.d/` | Additional config files |
| `/var/log/nginx/access.log` | Access logs |
| `/var/log/nginx/error.log` | Error logs |
| `/usr/share/nginx/html/` | Document root |
| `/etc/sysctl.conf` | Kernel parameters |
| `/etc/security/limits.conf` | User limits |

### System Information Commands

```bash
# CPU info
lscpu
nproc

# Memory
free -h
cat /proc/meminfo

# Disk I/O
lsblk
iostat -x 1

# Network
ip addr
ethtool eth0  # or actual interface name

# Open files limit
ulimit -n

# Current connections
ss -s
ss -tnp | grep nginx | wc -l

# Nginx worker processes
ps aux | grep nginx
```

## Benchmark Node Details

### Benchmark Tools

```bash
# Location of benchmark script
/root/benchmark.sh

# Hackathon tools
/root/hackathon-tools/
├── small.lua       # Small file workload
├── medium.lua      # Medium file workload
├── large.lua       # Large file workload
├── mixed.lua       # Mixed workload
├── parse_wrk_output.py
├── compare_results.py
└── README.md

# Results directory
/root/hackathon-results/
```

### Running Benchmarks

```bash
# Run full benchmark suite
./benchmark.sh <contestant-name>

# Compare results
./compare-results.sh <contestant-name>

# View results
ls /root/hackathon-results/
cat /root/hackathon-results/<contestant-name>_<workload>.json
```

## Network Topology

```
┌─────────────────────┐         ┌─────────────────────┐
│   Benchmark Node    │         │        DUT          │
│  (Load Generator)   │◄───────►│   (Nginx Server)    │
│                     │  HTTP   │                     │
│  e40-h37-...        │         │  e40-h34-...        │
│  wrk benchmark      │         │  nginx              │
└─────────────────────┘         └─────────────────────┘
         │                               │
         └───────────┬───────────────────┘
                     │
              Scalelab Network
```

## Pre-flight Checks

Run these before starting any work:

### On DUT (Nginx Server)

```bash
# 1. Check Nginx is running
systemctl status nginx

# 2. Check Nginx config is valid
nginx -t

# 3. Check listening ports
ss -tlnp | grep nginx

# 4. Check system resources
top -bn1 | head -20
free -h
df -h

# 5. Check kernel version
uname -r

# 6. Check RHEL version
cat /etc/redhat-release
```

### On Benchmark Node

```bash
# 1. Check wrk is installed
which wrk
wrk --version

# 2. Check connectivity to DUT
curl -s -o /dev/null -w "%{http_code}\n" http://test-machine/

# 3. Check Lua scripts exist
ls -la /root/hackathon-tools/*.lua

# 4. Run quick sanity test
wrk -t2 -c10 -d5s http://test-machine/
```

## Troubleshooting Access

### SSH Connection Refused

```bash
# Check if sshd is running on target
# (requires console access or another path)
systemctl status sshd
```

### Permission Denied

```bash
# Verify credentials
ssh -v root@hostname

# If using keys, check permissions
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_rsa.pub
```

### Network Unreachable

```bash
# Check if on VPN (if required)
# Check DNS resolution
nslookup e40-h34-000-r650.rdu2.scalelab.redhat.com

# Try IP directly if DNS fails
ping <IP-address>
```
