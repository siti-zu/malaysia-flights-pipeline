{% test greater_than_zero(model, column_name) %}

-- Fails for every row where the column is zero or negative. Nulls pass;
-- pair with not_null if the column must also be filled.
SELECT *
FROM {{ model }}
WHERE {{ column_name }} <= 0

{% endtest %}
