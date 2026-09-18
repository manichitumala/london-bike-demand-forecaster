-- Clean, typed view over the raw TfL journey extracts.
-- Drops journeys with an impossible duration (<=0s, a stuck/lost bike docked
-- back in after >24h) since those are data artefacts, not real trips.
CREATE OR REPLACE VIEW stg_journeys AS
SELECT
    "Number"                       AS journey_id,
    CAST("Start date" AS TIMESTAMP) AS start_ts,
    CAST("End date" AS TIMESTAMP)   AS end_ts,
    CAST("Start station number" AS INTEGER) AS start_station_id,
    "Start station"                AS start_station_name,
    CAST("End station number" AS INTEGER)   AS end_station_id,
    "End station"                  AS end_station_name,
    "Bike model"                   AS bike_model,
    "Total duration (ms)" / 1000.0 AS duration_seconds
FROM raw_journeys
WHERE "Total duration (ms)" > 0
  AND "Total duration (ms)" < 24 * 3600 * 1000
  AND "Start station number" IS NOT NULL
  AND "End station number" IS NOT NULL;
