-- One row per home airport and hour of the day (Malaysia time), with every
-- hour present even if it had no flights.
-- Departures are bucketed by first_seen and arrivals by last_seen, the closest
-- OpenSky gets to take-off and landing times.
WITH movements AS (
    SELECT
        est_departure_airport AS airport_code,
        EXTRACT(HOUR FROM first_seen_local)::int AS hour_of_day,
        'departure' AS direction
    FROM {{ ref('fct_flights') }}
    WHERE est_departure_airport IN ('{{ var("home_airports") | join("', '") }}')

    UNION ALL

    SELECT
        est_arrival_airport AS airport_code,
        EXTRACT(HOUR FROM last_seen_local)::int AS hour_of_day,
        'arrival' AS direction
    FROM {{ ref('fct_flights') }}
    WHERE est_arrival_airport IN ('{{ var("home_airports") | join("', '") }}')
),

airport_hours AS (
    SELECT airport_code, hour_of_day
    FROM UNNEST(ARRAY['{{ var("home_airports") | join("', '") }}']) AS airport_code
    CROSS JOIN generate_series(0, 23) AS hour_of_day
),

days AS (
    SELECT COUNT(DISTINCT flight_date) AS days_covered
    FROM {{ ref('fct_flights') }}
)

SELECT
    airport_hours.airport_code,
    dim_airport.airport_name,
    airport_hours.hour_of_day,
    COUNT(movements.direction) FILTER (WHERE movements.direction = 'departure') AS departures,
    COUNT(movements.direction) FILTER (WHERE movements.direction = 'arrival') AS arrivals,
    COUNT(movements.direction) AS movements,
    ROUND(COUNT(movements.direction)::numeric / MAX(days.days_covered), 1) AS avg_movements_per_day,
    RANK() OVER (
        PARTITION BY airport_hours.airport_code
        ORDER BY COUNT(movements.direction) DESC
    ) AS busiest_rank
FROM airport_hours
CROSS JOIN days
LEFT JOIN movements
    ON airport_hours.airport_code = movements.airport_code
   AND airport_hours.hour_of_day = movements.hour_of_day
LEFT JOIN {{ ref('dim_airport') }} AS dim_airport
    ON airport_hours.airport_code = dim_airport.airport_code
GROUP BY 1, 2, 3
