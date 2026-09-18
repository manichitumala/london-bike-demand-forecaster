-- Unified hourly weather: real historical observations, plus forecast rows
-- for any hour the archive doesn't cover yet (the live 7-day-ahead case).
CREATE OR REPLACE VIEW stg_weather AS
SELECT ts, temperature_2m, precipitation, rain, wind_speed_10m, relative_humidity_2m
FROM raw_weather_historical
UNION ALL
SELECT f.ts, f.temperature_2m, f.precipitation, f.rain, f.wind_speed_10m, f.relative_humidity_2m
FROM raw_weather_forecast f
WHERE f.ts NOT IN (SELECT ts FROM raw_weather_historical);

-- Model-ready feature table: one row per (station, hour), actuals plus the
-- 7-day forecast horizon, with calendar, weather and lagged-demand features.
-- Lags are computed over the full is_actual history so the horizon's
-- lag_168h_departures (exactly 7 days back) is always a real observed value.
CREATE OR REPLACE TABLE fct_features AS
SELECT
    f.station_id,
    f.hour_ts,
    f.is_actual,
    f.departures,
    f.arrivals,
    f.net_flow,
    hour(f.hour_ts)                                   AS hour_of_day,
    dayofweek(f.hour_ts)                               AS day_of_week,
    CASE WHEN dayofweek(f.hour_ts) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend,
    CASE WHEN bh.date IS NOT NULL THEN 1 ELSE 0 END    AS is_bank_holiday,
    w.temperature_2m,
    w.precipitation,
    w.rain,
    w.wind_speed_10m,
    w.relative_humidity_2m,
    LAG(f.departures, 1) OVER station_hours            AS lag_1h_departures,
    LAG(f.departures, 24) OVER station_hours            AS lag_24h_departures,
    LAG(f.departures, 168) OVER station_hours           AS lag_168h_departures,
    AVG(f.departures) OVER (
        PARTITION BY f.station_id ORDER BY f.hour_ts
        ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING
    )                                                   AS rolling_7d_avg_departures,
    LAG(f.arrivals, 1) OVER station_hours               AS lag_1h_arrivals,
    LAG(f.arrivals, 24) OVER station_hours              AS lag_24h_arrivals,
    LAG(f.arrivals, 168) OVER station_hours             AS lag_168h_arrivals,
    AVG(f.arrivals) OVER (
        PARTITION BY f.station_id ORDER BY f.hour_ts
        ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING
    )                                                   AS rolling_7d_avg_arrivals
FROM fct_hourly_station_demand f
LEFT JOIN stg_weather w ON w.ts = f.hour_ts
LEFT JOIN raw_bank_holidays bh ON bh.date = CAST(f.hour_ts AS DATE)
WINDOW station_hours AS (PARTITION BY f.station_id ORDER BY f.hour_ts);
