-- Hand-checked names for codes missing from OpenFlights. An override also
-- replaces the OpenFlights name if the same code ever appears in both.
WITH overrides AS (
    SELECT
        airline_code::text AS airline_code,
        airline_name::text AS airline_name
    FROM {{ ref('airline_overrides') }}
),

openflights AS (
    SELECT
        airline_code::text AS airline_code,
        airline_name::text AS airline_name
    FROM {{ ref('airlines') }}
    WHERE airline_code NOT IN (SELECT airline_code FROM overrides)
)

SELECT * FROM overrides
UNION ALL
SELECT * FROM openflights
