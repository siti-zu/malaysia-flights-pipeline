SELECT
    airline_code::text AS airline_code,
    airline_name::text AS airline_name
FROM {{ ref('airlines') }}