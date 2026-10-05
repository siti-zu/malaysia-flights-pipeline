SELECT 
    airport_code::text AS airport_code,
    airport_name::text AS airport_name,
    city::text AS city,
    country_code::text AS country_code,
    latitude::numeric AS latitude,
    longitude::numeric AS longitude
FROM {{ ref('airports') }}