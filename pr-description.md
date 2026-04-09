## Summary

- Remove `directio 512k` and `aio threads` from agent tuning recommendations — these bypass page cache and cause ~50% degradation on medium/large/mixed workloads when dataset fits in RAM
- Add `reuseport`, higher `worker_connections` (16384), `multi_accept on`, NIC ring buffer max (8192), busy polling, tcp_fastopen, and RPS to tuning knowledge base
- Update results to reflect improved numbers (all workloads now >300% improvement)

## Why remove `directio 512k`?

`directio` tells nginx to bypass the kernel page cache and read directly from disk. This is harmful in our environment because:

- **DUT has 502GB RAM**, total dataset is ~489GB — everything fits in page cache
- With `sendfile on`, nginx serves files at **memory speed** via page cache
- With `directio 512k`, every file >512KB (medium, large, mixed workloads) forces **actual disk I/O**, even though the data is already cached in RAM
- `aio threads` is only useful alongside `directio` — without it, `sendfile` is faster

**Measured impact on same machines (e26-h23 / e40-h33), same NIC, only difference is directio:**

| Workload | With directio (rps) | Without directio (rps) | Difference |
|----------|---------------------|------------------------|------------|
| homepage | 1,567,249 | 1,740,325 | +11% |
| small | 1,890,691 | 2,004,259 | +6% |
| medium | 2,921 | 5,595 | **+91%** |
| large | 410 | 745 | **+82%** |
| mixed | 4,884 | 8,981 | **+84%** |

**Rule**: Only use `directio` when dataset >> available RAM. When data fits in RAM, `sendfile` + page cache always wins.

## Other improvements

- **`reuseport`** on listen directive — eliminates accept mutex contention across 112 workers
- **`worker_connections 16384`** (was 4096) — higher headroom for concurrent connections
- **NIC ring buffers 8192** (was 2047) — uses hardware max, prevents packet drops under load
- **`busy_poll = 50`** — reduces network I/O latency
- **`tcp_fastopen = 3`** — enables TCP Fast Open for client+server
- **NIC offloads** (GRO/GSO/TSO) + adaptive coalescing + RPS enabled

## Test plan

- [ ] Run agent in pipeline mode on test machines, verify `directio` and `aio threads` are NOT in applied tunings
- [ ] Run agent in agentic mode, verify LLM does not recommend `directio`
- [ ] Compare before/after benchmark results on medium and large workloads
- [ ] Verify `reuseport` appears in nginx listen directive after tuning
