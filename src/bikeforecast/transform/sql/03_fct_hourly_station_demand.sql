-- Hourly demand per station: a complete (station x hour) grid, zero-filled
-- for hours with no trips, extended 168h (7 days) past the last real data
-- so the forecast horizon has rows to attach weather/calendar features to.
-- `is_actual` marks which rows are real counts vs. the future horizon to
-- be predicted.
CREATE OR REPLACE TABLE fct_hourly_station_demand AS
WITH bounds AS (
    SELECT
        date_trunc('hour', MIN(start_ts)) AS min_ts,
        date_trunc('hour', MAX(start_ts)) AS max_actual_ts,
        date_trunc('hour', MAX(start_ts)) + INTERVAL 168 HOUR AS max_grid_ts
    FROM stg_journeys
),
hours AS (
    SELECT unnest(generate_series(
        (SELECT min_ts FROM bounds),
        (SELECT max_grid_ts FROM bounds),
        INTERVAL 1 HOUR
    )) AS hour_ts
),
grid AS (
    SELECT h.hour_ts, s.station_id
    FROM hours h
    CROSS JOIN dim_stations s
),
departures AS (
    SELECT start_station_id AS station_id, date_trunc('hour', start_ts) AS hour_ts, COUNT(*) AS n
    FROM stg_journeys
    GROUP BY 1, 2
),
arrivals AS (
    SELECT end_station_id AS station_id, date_trunc('hour', end_ts) AS hour_ts, COUNT(*) AS n
    FROM stg_journeys
    GROUP BY 1, 2
)
SELECT
    g.station_id,
    g.hour_ts,
    g.hour_ts <= b.max_actual_ts AS is_actual,
    CASE WHEN g.hour_ts <= b.max_actual_ts THEN COALESCE(d.n, 0) END AS departures,
    CASE WHEN g.hour_ts <= b.max_actual_ts THEN COALESCE(a.n, 0) END AS arrivals,
    CASE WHEN g.hour_ts <= b.max_actual_ts THEN COALESCE(a.n, 0) - COALESCE(d.n, 0) END AS net_flow
FROM grid g
CROSS JOIN bounds b
LEFT JOIN departures d ON d.station_id = g.station_id AND d.hour_ts = g.hour_ts
LEFT JOIN arrivals a ON a.station_id = g.station_id AND a.hour_ts = g.hour_ts;
