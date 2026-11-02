-- One row per route (departure airport -> arrival airport), ranked by flights.
-- Only flights where both ends are known; see the README's data notes.
WITH routes AS (
    SELECT
        est_departure_airport AS departure_airport_code,
        est_arrival_airport AS arrival_airport_code,
        COUNT(*) AS flights
    FROM {{ ref('fct_flights') }}
    WHERE est_departure_airport IS NOT NULL
      AND est_arrival_airport IS NOT NULL
      AND est_departure_airport <> est_arrival_airport
    GROUP BY 1, 2
)

SELECT
    RANK() OVER (ORDER BY routes.flights DESC) AS route_rank,
    routes.departure_airport_code || '-' || routes.arrival_airport_code AS route,
    routes.departure_airport_code,
    dep.airport_name AS departure_airport_name,
    dep.city AS departure_city,
    dep.country_code AS departure_country_code,
    routes.arrival_airport_code,
    arr.airport_name AS arrival_airport_name,
    arr.city AS arrival_city,
    arr.country_code AS arrival_country_code,
    routes.flights
FROM routes
LEFT JOIN {{ ref('dim_airport') }} AS dep ON routes.departure_airport_code = dep.airport_code
LEFT JOIN {{ ref('dim_airport') }} AS arr ON routes.arrival_airport_code = arr.airport_code
