SELECT
    airport_code,
    airport_name,
    city,
    country_code,
    latitude,
    longitude
FROM {{ ref('stg_airports') }}
