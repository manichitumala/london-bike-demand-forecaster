-- One row per docking station that appears in the journey history, with the
-- most frequently used name for that terminal id and a lat/lon/capacity
-- joined from the live BikePoint snapshot (terminal ids match on the
-- numeric part of TerminalName). Stations with no BikePoint match (closed
-- since the journeys were recorded) keep NULL lat/lon.
CREATE OR REPLACE TABLE dim_stations AS
WITH journey_stations AS (
    SELECT start_station_id AS station_id, start_station_name AS station_name FROM stg_journeys
    UNION ALL
    SELECT end_station_id, end_station_name FROM stg_journeys
),
ranked_names AS (
    SELECT
        station_id,
        station_name,
        COUNT(*) AS n,
        ROW_NUMBER() OVER (PARTITION BY station_id ORDER BY COUNT(*) DESC) AS rn
    FROM journey_stations
    GROUP BY station_id, station_name
)
SELECT
    rn.station_id,
    rn.station_name,
    bp.lat,
    bp.lon,
    bp.nb_docks AS capacity
FROM ranked_names rn
LEFT JOIN raw_stations bp
    ON TRY_CAST(bp.terminal_name AS INTEGER) = rn.station_id
WHERE rn.rn = 1;
