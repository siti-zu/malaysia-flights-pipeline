-- One row per airline code, ranked by flights. Flights with no callsign are
-- grouped under a null airline_code; codes that aren't airlines (private and
-- military callsigns) keep their code with a null airline_name.
WITH per_airline AS (
    SELECT
        airline_code,
        COUNT(*) AS flights
    FROM {{ ref('fct_flights') }}
    GROUP BY 1
)

SELECT
    RANK() OVER (ORDER BY per_airline.flights DESC) AS airline_rank,
    per_airline.airline_code,
    dim_airline.airline_name,
    per_airline.flights,
    ROUND(100.0 * per_airline.flights / SUM(per_airline.flights) OVER (), 2) AS share_of_flights_pct
FROM per_airline
LEFT JOIN {{ ref('dim_airline') }} AS dim_airline
    ON per_airline.airline_code = dim_airline.airline_code
