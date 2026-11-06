"""Synthetic but realistic incident history for Northwind Pay.

Everything here is fictional. The data is deliberately specific: real log
lines, exact commands, real-sounding responders, and the actions that made
each incident worse. That specificity is what makes the memory demo land.
"""

from __future__ import annotations

from typing import Any

INCIDENTS: list[dict[str, Any]] = [
    {
        "id": "INC-2041",
        "date": "2026-03-04T02:14:00Z",
        "service": "checkout-api",
        "title": "Checkout 502 spike after v2.31.0: Hikari pool exhausted by a connection leak",
        "symptoms": (
            "02:14 UTC: checkout-api 5xx rate 14% (baseline 0.3%), p95 latency 8.1s.\n"
            "02:16 UTC: HikariPool-1 - Connection is not available, request timed out after 30000ms.\n"
            "02:17 UTC: Postgres active connections 188/200, most held by checkout-api pods.\n"
            "02:22 UTC: deploy v2.31.0 completed six minutes before the first alert."
        ),
        "root_cause": (
            "v2.31.0 reduced hikari maximumPoolSize from 40 to 8 and leaked a connection in the new "
            "promo-code branch, so requests queued for a connection until the 30s timeout."
        ),
        "resolution": [
            '`deploy rollback --service checkout-api --to v2.30.4 --reason "v2.31.0 pool regression"` — 5xx back under 1% in 6 minutes.',
            "Confirm saturation: `kubectl exec deploy/checkout-api -- curl -s localhost:8080/actuator/metrics/hikaricp.connections.pending`.",
            "Restore `DB_POOL_MAX=40` in config and recycle pods one at a time: `kubectl rollout restart deploy/checkout-api`.",
            "Fix the leaked `Connection` in `PromoCodeRepository` with try-with-resources and ship v2.30.5.",
        ],
        "what_failed": [
            "Scaled replicas 6 -> 18: each pod opened its own 40-connection pool, Postgres hit max_connections=200, and the 5xx rate rose from 11% to 34%.",
            "Restarted all pods at once: the pool re-leaked within 4 minutes and the 502s returned.",
            "Raised maximumPoolSize to 100: Postgres CPU pinned at 100% and p99 latency doubled.",
        ],
        "ttr_minutes": 38,
        "responder": "Priya Nair",
    },
    {
        "id": "INC-2057",
        "date": "2026-03-21T18:40:00Z",
        "service": "payments-gateway",
        "title": "Payments gateway mTLS outage: expired client certificate rejected by PSP",
        "symptoms": (
            "18:40 UTC: payment authorization success rate fell from 99.2% to 12%.\n"
            "18:41 UTC: x509: certificate signed by unknown authority (client cert CN=payments-gateway.northwindpay.internal).\n"
            "18:42 UTC: TLS handshake with api.payments-processor.example:443 failed: certificate has expired."
        ),
        "root_cause": (
            "The gateway's client certificate in secret payments-gateway-tls expired at 18:00 UTC; the PSP "
            "rejected the mTLS handshake and authorizations failed closed."
        ),
        "resolution": [
            "Confirm expiry: `kubectl get secret payments-gateway-tls -o jsonpath='{.data.tls\\.crt}' | base64 -d | openssl x509 -noout -enddate`.",
            "Install the renewed cert: `kubectl create secret tls payments-gateway-tls --cert=new.crt --key=new.key --dry-run=client -o yaml | kubectl apply -f -`.",
            "Recycle the gateway and verify mTLS: `kubectl rollout restart deploy/payments-gateway` then `openssl s_client -connect api.payments-processor.example:443 -cert new.crt -key new.key`.",
            "Replay failed authorizations from the DLQ only after the PSP confirms deduplication by idempotency key.",
        ],
        "what_failed": [
            "Restarted the gateway before rotating the certificate: pods came up with the same expired cert and stayed down.",
            "Disabled TLS verification in the PSP client to restore traffic: blocked by security policy and would have exposed card data.",
        ],
        "ttr_minutes": 31,
        "responder": "Daniel Okafor",
    },
    {
        "id": "INC-2068",
        "date": "2026-04-02T09:05:00Z",
        "service": "redis-cache",
        "title": "Redis eviction storm logged out 23% of active sessions",
        "symptoms": (
            "09:05 UTC: auth-service 401 rate 23% (baseline 0.4%); session lookup misses 61%.\n"
            "09:06 UTC: redis-cache used_memory 3.98GB / 4GB, evicted_keys +180k/min, maxmemory-policy allkeys-lru.\n"
            "09:08 UTC: auth-service logged \"session not found for valid JWT\" 4,120 times/min."
        ),
        "root_cause": (
            "A marketing campaign doubled traffic and filled redis-cache; allkeys-lru evicted session keys "
            "alongside cached product data, so valid JWTs had no server-side session."
        ),
        "resolution": [
            "`redis-cli CONFIG SET maxmemory-policy volatile-lru` so only keys with a TTL are evicted.",
            "Warm active sessions by replaying valid JWTs through auth-service, then confirm `redis-cli INFO keyspace` has `sess:*` keys again.",
            "`redis-cli CONFIG SET maxmemory 6gb` and add a read replica before the next campaign.",
            "Alert at 70% memory and move sessions to a dedicated Redis logical database.",
        ],
        "what_failed": [
            "Ran `redis-cli FLUSHALL`: it logged out every user and triggered a 9x login storm.",
            "Restarted Redis: the empty cache caused a thundering herd and auth p99 hit 22s.",
        ],
        "ttr_minutes": 44,
        "responder": "Sofia Alvarez",
    },
    {
        "id": "INC-2076",
        "date": "2026-04-09T10:14:00Z",
        "service": "auth-service",
        "title": "Auth-service rejected valid JWTs after clock drift on three nodes",
        "symptoms": (
            "10:14 UTC: auth-service 401 rate 31% (baseline 0.7%); login success down 44%.\n"
            "10:15 UTC: JwtValidationService: JWT rejected: token is not valid yet (iat=2026-04-09T10:21:03Z).\n"
            "10:16 UTC: 3 of 6 auth-service nodes reported NTP offset 6-8 minutes; chrony marked unsynchronised.\n"
            "10:18 UTC: retries from mobile clients amplified traffic 3.4x."
        ),
        "root_cause": (
            "The node pool's NTP source failed after a network change and three auth-service nodes drifted "
            "6-8 minutes ahead; they rejected freshly issued JWTs as 'not valid yet'."
        ),
        "resolution": [
            "Confirm skew per node: `kubectl exec deploy/auth-service -- chronyc tracking` (look at System time offset).",
            "Repoint chrony at the internal NTP pool and force a step: `chronyc makestep`, then verify offset is under 1s.",
            "Roll auth-service nodes one at a time so no quorum of skewed nodes remains.",
            "Add 60s of `iat` leeway in JwtValidationService and alert when any node's NTP offset exceeds 5s.",
        ],
        "what_failed": [
            "Restarted all auth-service pods at once: the replacements landed on the same unsynchronised nodes and the 401s continued.",
            "Disabled JWT expiry/iat validation to restore logins: security blocked it as an authentication bypass.",
            "Scaled auth-service 6 -> 18: eight of the new nodes also had bad clocks and the failure rate rose to 38%.",
        ],
        "ttr_minutes": 34,
        "responder": "Sofia Alvarez",
    },
    {
        "id": "INC-2081",
        "date": "2026-04-18T23:12:00Z",
        "service": "orders-db",
        "title": "Orders read replica canceling queries during recovery conflict",
        "symptoms": (
            "23:12 UTC: order-history API 500 rate 9%; reads routed to orders-db-replica-1.\n"
            "23:13 UTC: FATAL: canceling statement due to conflict with recovery.\n"
            "23:13 UTC: DETAIL: User query might have needed to see row versions that must be removed.\n"
            "23:14 UTC: replica replay lag 1.8GB; monthly_report query running 41 minutes."
        ),
        "root_cause": (
            "An unbounded monthly reporting query on the read replica held a snapshot while WAL replay needed "
            "to remove rows, causing recovery conflicts that cancelled order-history queries."
        ),
        "resolution": [
            "Cancel only the reporting query: `SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE query LIKE '%monthly_report%' AND state='active';`.",
            "Set `max_standby_streaming_delay='30s'` and `hot_standby_feedback=on`, then `SELECT pg_reload_conf();`.",
            "Move reporting to the warehouse and set `statement_timeout=120s` on the reporting role.",
            "Fail reads over to the primary only if the error rate stays above 5% for 10 minutes.",
        ],
        "what_failed": [
            "Ran `SELECT pg_terminate_backend(pid) FROM pg_stat_activity` for every connection: it killed the API pool and took order history down for 12 minutes.",
            "Promoted the replica: it was 4 minutes behind and duplicated 1,900 order events.",
        ],
        "ttr_minutes": 52,
        "responder": "Wei Zhang",
    },
    {
        "id": "INC-2096",
        "date": "2026-05-09T14:08:00Z",
        "service": "search-indexer",
        "title": "Search indexer rejected documents after an incompatible mapping change",
        "symptoms": (
            "14:08 UTC: product search results stale; 0 documents indexed in 26 minutes.\n"
            "14:09 UTC: mapper_parsing_exception: failed to parse field [price] of type [keyword] in document with id 88213.\n"
            "14:10 UTC: indexer lag 214k documents; bulk queue depth 1.9M."
        ),
        "root_cause": (
            "A schema migration changed price from keyword to scaled_float on the live index, and Elasticsearch "
            "rejected every document that carried the new numeric value."
        ),
        "resolution": [
            "Create `products_v7` with the new mapping and `number_of_replicas=0` during the build.",
            "Reindex: `curl -X POST localhost:9200/_reindex -H 'Content-Type: application/json' -d '{\"source\":{\"index\":\"products_v6\"},\"dest\":{\"index\":\"products_v7\"}}'`.",
            "Swap atomically: `curl -X POST localhost:9200/_aliases -d '{\"actions\":[{\"remove\":{\"index\":\"products_v6\",\"alias\":\"products\"}},{\"add\":{\"index\":\"products_v7\",\"alias\":\"products\"}}]}'`.",
            "Restore replicas: `PUT /products_v7/_settings {\"number_of_replicas\":2}`, then replay the indexer DLQ.",
        ],
        "what_failed": [
            "Deleted and recreated the live index in place: search returned zero results for 19 minutes.",
            "Ran a force merge during reindex: disk I/O saturated and the indexer fell a further 90k documents behind.",
        ],
        "ttr_minutes": 67,
        "responder": "Aisha Rahman",
    },
    {
        "id": "INC-2110",
        "date": "2026-05-27T16:22:00Z",
        "service": "notification-worker",
        "title": "Notification backlog after SES throttling triggered a retry storm",
        "symptoms": (
            "16:22 UTC: notification-worker queue depth 480k and rising 12k/min.\n"
            "16:23 UTC: SES 454 Throttling: Maximum sending rate exceeded.\n"
            "16:24 UTC: retry attempts per message reached 38; worker CPU 94%, no dead-letter queue configured."
        ),
        "root_cause": (
            "A price-drop campaign pushed 3x normal volume; SES throttled the worker and fixed-delay retries "
            "amplified the load until the queue backed up."
        ),
        "resolution": [
            "Pause the campaign producer: `kubectl scale deploy/campaign-scheduler --replicas=0`.",
            "Route failures to a DLQ and enable exponential backoff with jitter: `RETRY_BASE_MS=500 RETRY_MAX_MS=60000 RETRY_JITTER=true`.",
            "Request a temporary SES quota increase and replay the DLQ in batches of 500.",
            "Add a queue-depth alarm at 100k and a per-campaign rate limit.",
        ],
        "what_failed": [
            "Purged the queue to clear the backlog: 41,000 password-reset and payment-receipt emails were lost.",
            "Raised worker concurrency from 20 to 200: SES throttled harder and the retry storm doubled.",
        ],
        "ttr_minutes": 73,
        "responder": "Daniel Okafor",
    },
    {
        "id": "INC-2124",
        "date": "2026-06-15T11:47:00Z",
        "service": "checkout-api",
        "title": "Checkout latency spike: missing index held pool connections during promo traffic",
        "symptoms": (
            "11:47 UTC: checkout p95 7.8s, 5xx 6%; HikariPool-1 pending 48.\n"
            "11:48 UTC: slow query 29.6s: SELECT ... FROM orders WHERE payment_intent_id = $1.\n"
            "11:49 UTC: orders table 84M rows, sequential scan on payment_intent_id; promo traffic 2.7x baseline."
        ),
        "root_cause": (
            "The promo drove 2.7x traffic, and a missing index on orders(payment_intent_id) made every payment "
            "lookup a sequential scan; slow queries held pool connections until checkout timed out."
        ),
        "resolution": [
            "Create the index without blocking writes: `CREATE INDEX CONCURRENTLY idx_orders_payment_intent_id ON orders(payment_intent_id);`.",
            "Confirm the plan: `EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM orders WHERE payment_intent_id = 'pi_...';`.",
            "Raise `DB_POOL_MAX` 40 -> 60 only while the index builds, then set it back.",
            "Cache payment-intent lookups for 30s and alert when query p95 exceeds 500ms.",
        ],
        "what_failed": [
            "Scaled checkout-api 8 -> 24 replicas: each new pod opened a 40-connection pool and Postgres hit 960/1000 connections.",
            "Restarted the pods: the same slow query re-filled the pool within 5 minutes.",
        ],
        "ttr_minutes": 29,
        "responder": "Priya Nair",
    },
    {
        "id": "INC-2139",
        "date": "2026-09-08T03:31:00Z",
        "service": "checkout-api",
        "title": "Checkout 502 spike after v3.4.1: pool exhaustion from a blocking FX call",
        "symptoms": (
            "03:31 UTC: checkout-api 5xx 18%, p95 9.4s, success rate down 41%.\n"
            "03:32 UTC: HikariPool-1 - Connection is not available, request timed out after 30000ms.\n"
            "03:33 UTC: FX client POST /v1/rates timed out at 30s inside an open DB transaction.\n"
            "03:34 UTC: v3.4.1 deployed 7 minutes before the alert; pool max lowered 40 -> 12."
        ),
        "root_cause": (
            "v3.4.1 lowered hikari maximumPoolSize to 12 and added a synchronous FX-rate lookup inside the "
            "payment transaction; when FX slowed, every request held a DB connection for 30s and the pool exhausted."
        ),
        "resolution": [
            '`deploy rollback --service checkout-api --to v3.4.0 --reason "pool exhaustion after v3.4.1"` — 5xx normalized in 6 minutes.',
            "Check pool pressure: `kubectl exec deploy/checkout-api -- curl -s localhost:8080/actuator/metrics/hikaricp.connections.pending`.",
            "Restore `DB_POOL_MAX=40` and `DB_CONNECTION_TIMEOUT_MS=2000`, then roll pods one at a time.",
            "Move the FX lookup out of the transaction and wrap it in a circuit breaker before shipping v3.4.2.",
        ],
        "what_failed": [
            "Scaled checkout 8 -> 20 replicas: DB connections hit 480/500 and p99 rose to 14s.",
            "Restarted all checkout pods: the pool re-exhausted in under 3 minutes.",
            "Raised the pool to 80 without fixing the blocking FX call: Postgres CPU hit 97%.",
        ],
        "ttr_minutes": 26,
        "responder": "Marcus Bell",
    },
    {
        "id": "INC-2152",
        "date": "2026-07-04T07:19:00Z",
        "service": "kafka-ingest",
        "title": "Kafka ingest lag after a hot partition and a broker disk bottleneck",
        "symptoms": (
            "07:19 UTC: kafka-ingest consumer lag 4.2M messages on payments.events.v2; 2 of 24 partitions hot.\n"
            "07:20 UTC: broker-3 disk await 480ms; log dir on a 92% full volume.\n"
            "07:21 UTC: consumer group rebalanced 11 times in 10 minutes."
        ),
        "root_cause": (
            "Payment events keyed by merchant_id sent 61% of traffic to two partitions; broker-3's full disk "
            "slowed fetches, consumers timed out and rebalanced repeatedly."
        ),
        "resolution": [
            "Free broker disk by moving old segments or applying retention after approval: `kafka-log-dirs.sh --describe`.",
            "Change the producer key to `merchant_id:payment_intent_id` so partitions spread.",
            "Increase partitions from 24 to 48 in a maintenance window and let the group rebalance once.",
            "Set `max.poll.interval.ms=600000` and tune `fetch.max.bytes` while the backlog drains.",
        ],
        "what_failed": [
            "Reset consumer offsets to latest: 1.1M payment events were skipped and had to be reconciled manually.",
            "Purged the topic: 6 hours of payment events were lost and downstream ledgers diverged.",
        ],
        "ttr_minutes": 96,
        "responder": "Aisha Rahman",
    },
    {
        "id": "INC-2183",
        "date": "2026-10-01T05:44:00Z",
        "service": "orders-db",
        "title": "Orders primary disk full from an inactive replication slot retaining WAL",
        "symptoms": (
            "05:44 UTC: orders-db primary disk 99.8% full; Postgres read-only, writes failing.\n"
            "05:45 UTC: FATAL: could not write to file \"pg_wal/00000001000004A1000000B8\": No space left on device.\n"
            "05:46 UTC: replication slot analytics_slot inactive for 19 days, retaining 214GB WAL."
        ),
        "root_cause": (
            "An abandoned analytics replication slot held WAL for 19 days; the primary's 1TB volume filled and "
            "Postgres switched to read-only."
        ),
        "resolution": [
            "Identify the slot: `SELECT slot_name, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) FROM pg_replication_slots;`.",
            "After confirming the analytics consumer is retired, drop it: `SELECT pg_drop_replication_slot('analytics_slot');` — WAL is released immediately.",
            "Archive WAL to object storage and set `max_slot_wal_keep_size='50GB'` so a stale slot cannot fill the disk again.",
            "Alert at 75% disk usage and check for inactive slots older than 24h.",
        ],
        "what_failed": [
            "Deleted files from pg_wal with `rm`: the primary crashed on the next checkpoint and the replica could not catch up.",
            "Promoted the replica with a 12-minute lag: 8,400 orders were written to the old primary and lost.",
        ],
        "ttr_minutes": 61,
        "responder": "Wei Zhang",
    },
]

POLICIES: list[dict[str, str]] = [
    {
        "id": "POL-101",
        "date": "2026-02-18T09:00:00Z",
        "text": (
            "Briefings must make known harmful actions explicit and prominent; never bury them under generic "
            "remediation. On-call engineers have followed plausible-but-harmful steps from generic runbooks, "
            "and the 'what made it worse' list is the highest-value part of a brief."
        ),
    },
    {
        "id": "POL-102",
        "date": "2026-02-18T09:05:00Z",
        "text": (
            "If the payments error rate exceeds 5% for 5 consecutive minutes, page the payments lead Anika Rao "
            "in #inc-payments within 10 minutes. Do not wait for the next standup or for a second confirmation."
        ),
    },
    {
        "id": "POL-103",
        "date": "2026-02-18T09:10:00Z",
        "text": (
            "Never purge a queue or reset Kafka consumer offsets without an approved replay plan and data-loss "
            "sign-off from the service owner. Purging and offset resets caused the two largest data-loss events "
            "at Northwind Pay."
        ),
    },
    {
        "id": "POL-104",
        "date": "2026-02-18T09:15:00Z",
        "text": (
            "If an incident starts within 60 minutes of a deploy, rollback is the default first action; get "
            "release-captain approval in #inc-deploy. For checkout-api escalations page Marcus Bell (checkout "
            "on-call); for orders-db page Wei Zhang (DBA rotation)."
        ),
    },
]

DEMO_ALERTS: dict[str, dict[str, str]] = {
    "checkout-api 502 spike (connection pool)": {
        "service": "checkout-api",
        "alert": (
            "Checkout API 5xx rate 18% for 8 minutes (SLO 1%); p95 latency 9.4s; "
            "checkout success rate down 41%."
        ),
        "logs": (
            "2026-10-14T02:11:48Z checkout-api-7f9c4d8b6-x2vqn ERROR HikariPool-1 - Connection is not available, request timed out after 30000ms.\n"
            "2026-10-14T02:11:49Z checkout-api-7f9c4d8b6-x2vqn WARN  c.n.p.checkout.PaymentOrchestrator - downstream call failed: POST /v1/payment-intents status=504 elapsed=30012ms\n"
            "2026-10-14T02:12:03Z checkout-api-7f9c4d8b6-x2vqn ERROR o.s.w.s.h.ExceptionTranslationFilter - Servlet.service() threw exception: java.sql.SQLTransientConnectionException\n"
            "2026-10-14T02:12:04Z deploy-bot INFO  v3.4.1 rolled out to checkout-api (image sha 9f2c1a7) 6m before alert\n"
            "2026-10-14T02:12:19Z checkout-api-7f9c4d8b6-x2vqn WARN  c.n.p.checkout.FxRateClient - POST /v1/rates timed out after 30000ms"
        ),
    },
    "payments-gateway mTLS failures (certificate)": {
        "service": "payments-gateway",
        "alert": (
            "Payment authorization success rate 12% (baseline 99.2%); PSP handshake failures "
            "across all gateway pods."
        ),
        "logs": (
            "2026-10-14T18:41:02Z payments-gateway-5c8f7d9b4-lm4rt ERROR c.n.p.gateway.PspClient - x509: certificate signed by unknown authority\n"
            "2026-10-14T18:41:02Z payments-gateway-5c8f7d9b4-lm4rt ERROR c.n.p.gateway.PspClient - TLS handshake failed with api.payments-processor.example:443\n"
            "2026-10-14T18:42:15Z payments-gateway-5c8f7d9b4-lm4rt WARN  c.n.p.gateway.PspClient - certificate for *.payments-processor.example expired 2026-10-13T23:59:59Z"
        ),
    },
    "orders-db recovery conflict (replica)": {
        "service": "orders-db",
        "alert": (
            "Order-history API 500 rate 9%; reads on orders-db-replica-1 failing; "
            "replica replay lag 1.8GB."
        ),
        "logs": (
            "2026-10-14T23:13:07Z orders-db-replica-1 FATAL: canceling statement due to conflict with recovery\n"
            "2026-10-14T23:13:07Z orders-db-replica-1 DETAIL: User query might have needed to see row versions that must be removed.\n"
            "2026-10-14T23:14:01Z orders-db-replica-1 LOG: streaming replication lag 1.8GB; active query monthly_report running 41m"
        ),
    },
    "kafka-ingest consumer lag (hot partition)": {
        "service": "kafka-ingest",
        "alert": (
            "payments.events.v2 consumer lag 4.2M messages and rising; 2 of 24 partitions hot; "
            "consumer group rebalancing repeatedly."
        ),
        "logs": (
            "2026-10-14T07:19:44Z kafka-ingest-3 WARN  o.a.k.c.c.i.ConsumerCoordinator - Offset commit failed: group rebalance in progress\n"
            "2026-10-14T07:20:02Z kafka-ingest-3 WARN  o.a.k.c.c.i.ConsumerCoordinator - Aborted rebalance: member took too long to rejoin\n"
            "2026-10-14T07:20:31Z kafka-ingest-3 ERROR c.n.p.ingest.PaymentConsumer - lag=4201882 partitions=[7,19] broker-3 disk.await=480ms volume=92%"
        ),
    },
}


def incident_to_document(incident: dict[str, Any]) -> str:
    """Render one incident as a single text document for Hindsight retain()."""
    steps = "\n".join(f"{i}. {step}" for i, step in enumerate(incident["resolution"], 1))
    failed = "\n".join(f"- {item}" for item in incident["what_failed"])
    return (
        f"Incident ID: {incident['id']}\n"
        f"Date: {incident['date']}\n"
        f"Service: {incident['service']}\n"
        f"Title: {incident['title']}\n"
        f"Symptoms:\n{incident['symptoms']}\n"
        f"Root cause: {incident['root_cause']}\n"
        f"Resolution:\n{steps}\n"
        f"What failed (made it worse):\n{failed}\n"
        f"TTR: {incident['ttr_minutes']} minutes\n"
        f"Responder: {incident['responder']}"
    )


def policy_to_document(policy: dict[str, str]) -> str:
    """Render one team policy as a memory document."""
    return f"Policy ID: {policy['id']}\nDate: {policy['date']}\nTeam policy: {policy['text']}"
