-- One row per home airport and day (Malaysia time), with every day present even
-- if it had no flights, so gaps show as zeros instead of missing rows.
-- Departures are dated by first_seen and arrivals by last_seen, as in rpt_busiest_hours.
-- A query_date is a UTC day and Malaysia is 8 hours ahead, so the first date is
-- missing its first 8 hours and the day after the last date is mostly missing.
-- Only fully covered days are kept, so a trend doesn't end in a false drop.
WITH movements AS (
    SELECT
        est_departure_airport AS airport_code,
        first_seen_local::date AS traffic_date,
        'departure' AS direction
    FROM {{ ref('fct_flights') }}
    WHERE est_departure_airport IN ('{{ var("home_airports") | join("', '") }}')

    UNION ALL

    SELECT
        est_arrival_airport AS airport_code,
        last_seen_local::date AS traffic_date,
        'arrival' AS direction
    FROM {{ ref('fct_flights') }}
    WHERE est_arrival_airport IN ('{{ var("home_airports") | join("', '") }}')
),

coverage AS (
    SELECT
        MIN(query_date) + 1 AS first_full_day,
        MAX(query_date) AS last_full_day
    FROM {{ ref('stg_flights') }}
),

airport_days AS (
    SELECT airport_code, day::date AS traffic_date
    FROM UNNEST(ARRAY['{{ var("home_airports") | join("', '") }}']) AS airport_code
    CROSS JOIN coverage
    CROSS JOIN generate_series(coverage.first_full_day, coverage.last_full_day, interval '1 day') AS day
),

daily AS (
    SELECT
        airport_days.airport_code,
        airport_days.traffic_date,
        COUNT(movements.direction) FILTER (WHERE movements.direction = 'departure') AS departures,
        COUNT(movements.direction) FILTER (WHERE movements.direction = 'arrival') AS arrivals,
        COUNT(movements.direction) AS movements
    FROM airport_days
    LEFT JOIN movements
        ON airport_days.airport_code = movements.airport_code
       AND airport_days.traffic_date = movements.traffic_date
    GROUP BY 1, 2
)

SELECT
    daily.airport_code,
    dim_airport.airport_name,
    daily.traffic_date,
    daily.departures,
    daily.arrivals,
    daily.movements,
    -- Null until there are 7 days to average, so early values aren't based on fewer.
    CASE
        WHEN COUNT(*) OVER last_7_days = 7 THEN ROUND(AVG(daily.movements) OVER last_7_days, 1)
    END AS movements_7_day_avg
FROM daily
LEFT JOIN {{ ref('dim_airport') }} AS dim_airport
    ON daily.airport_code = dim_airport.airport_code
WINDOW last_7_days AS (
    PARTITION BY daily.airport_code
    ORDER BY daily.traffic_date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
)
