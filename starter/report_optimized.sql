-- Task 4 optimized report.
--
-- The original query scans the same tables again for every output row. This
-- version scans each source into a small set of grouped CTEs, then joins those
-- groups once. It uses the single expression index created by
-- apply_report_indexes.py and adds no materialized reporting tables.

WITH
report_lines AS MATERIALIZED (
    SELECT
        line_id,
        tenant_id,
        customer_id,
        channel,
        substr(created_at, 1, 10) AS day
    FROM order_line
    WHERE substr(created_at, 1, 10) BETWEEN '2026-05-01' AND '2026-06-30'
),

-- One row per tenant/channel/day for values that only use order_line.
line_groups AS (
    SELECT
        tenant_id,
        channel,
        day,
        COUNT(DISTINCT line_id) AS lines_total,
        COUNT(DISTINCT customer_id) AS distinct_customers
    FROM report_lines
    GROUP BY tenant_id, channel, day
),

-- Add the order-line channel once instead of repeating this join in correlated
-- subqueries.
report_events AS MATERIALIZED (
    SELECT
        me.event_id,
        me.tenant_id,
        me.line_id,
        me.item_code,
        me.score,
        me.accepted,
        me.latency_ms,
        substr(me.created_at, 1, 10) AS day,
        rl.channel
    FROM match_event AS me
    JOIN report_lines AS rl ON rl.line_id = me.line_id
),

event_channel_groups AS (
    SELECT
        tenant_id,
        channel,
        day,
        COUNT(DISTINCT CASE WHEN accepted = 1 THEN line_id END) AS lines_accepted,
        COUNT(*) AS candidates_considered
    FROM report_events
    GROUP BY tenant_id, channel, day
),

event_day_groups AS (
    SELECT
        tenant_id,
        day,
        AVG(CASE WHEN accepted = 1 THEN score END) AS avg_accept_score,
        MAX(latency_ms) AS max_latency_ms,
        AVG(latency_ms) AS avg_latency_ms
    FROM report_events
    GROUP BY tenant_id, day
),

-- Only accepted events need an item lookup. Joining item for every candidate
-- would perform roughly ten times more index probes.
accepted_disabled_groups AS (
    SELECT
        re.tenant_id,
        re.day,
        COUNT(*) AS accepted_disabled
    FROM report_events AS re
    JOIN item AS it
      ON it.tenant_id = re.tenant_id
     AND it.item_code = re.item_code
    WHERE re.accepted = 1
      AND it.disabled = 1
    GROUP BY re.tenant_id, re.day
),

-- The first latency whose cumulative distribution reaches 95% is the
-- nearest-rank p95. This requires one partition sort.
latency_ranked AS (
    SELECT
        tenant_id,
        day,
        latency_ms,
        CUME_DIST() OVER (
            PARTITION BY tenant_id, day
            ORDER BY latency_ms
        ) AS latency_fraction
    FROM report_events
),
latency_p95 AS (
    SELECT
        tenant_id,
        day,
        MIN(CASE WHEN latency_fraction >= 0.95 THEN latency_ms END)
            AS p95_latency_ms
    FROM latency_ranked
    GROUP BY tenant_id, day
),

-- This scan starts one day before the report so 1 May can be compared with
-- 30 April. DISTINCT shrinks 560k+ events before the self-join.
day_items AS MATERIALIZED (
    SELECT DISTINCT
        tenant_id,
        substr(created_at, 1, 10) AS day,
        item_code
    FROM match_event
    WHERE substr(created_at, 1, 10) BETWEEN '2026-04-30' AND '2026-06-30'
),
repeat_item_groups AS (
    SELECT
        current.tenant_id,
        current.day,
        COUNT(*) AS repeat_items_prev_day
    FROM day_items AS current
    JOIN day_items AS previous
      ON previous.tenant_id = current.tenant_id
     AND previous.item_code = current.item_code
     AND previous.day = date(current.day, '-1 day')
    WHERE current.day BETWEEN '2026-05-01' AND '2026-06-30'
    GROUP BY current.tenant_id, current.day
)

SELECT
    lg.tenant_id,
    t.plan,
    lg.channel,
    lg.day,
    lg.lines_total,
    COALESCE(ecg.lines_accepted, 0) AS lines_accepted,
    COALESCE(ecg.candidates_considered, 0) AS candidates_considered,
    edg.avg_accept_score,
    edg.max_latency_ms,
    lp.p95_latency_ms,
    edg.avg_latency_ms,
    lg.distinct_customers,
    COALESCE(rig.repeat_items_prev_day, 0) AS repeat_items_prev_day,
    COALESCE(adg.accepted_disabled, 0) AS accepted_disabled
FROM line_groups AS lg
JOIN tenant AS t ON t.tenant_id = lg.tenant_id
LEFT JOIN event_channel_groups AS ecg
  ON ecg.tenant_id = lg.tenant_id
 AND ecg.channel = lg.channel
 AND ecg.day = lg.day
LEFT JOIN event_day_groups AS edg
  ON edg.tenant_id = lg.tenant_id
 AND edg.day = lg.day
LEFT JOIN latency_p95 AS lp
  ON lp.tenant_id = lg.tenant_id
 AND lp.day = lg.day
LEFT JOIN accepted_disabled_groups AS adg
  ON adg.tenant_id = lg.tenant_id
 AND adg.day = lg.day
LEFT JOIN repeat_item_groups AS rig
  ON rig.tenant_id = lg.tenant_id
 AND rig.day = lg.day
ORDER BY lg.tenant_id, lg.channel, lg.day;
