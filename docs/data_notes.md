**Which fields does each flight have, and which ones are sometimes null?**
["icao24", "firstSeen", "estDepartureAirport", "lastSeen", "estArrivalAirport", "callsign", "estDepartureAirportHorizDistance", "estDepartureAirportVertDistance", "estArrivalAirportHorizDistance", "estArrivalAirportVertDistance", "departureAirportCandidatesCount", "arrivalAirportCandidatesCount"].  
Sometimes null are estDepartureAirport, estDepartureAirportHorizDistance, and estDepartureAirportVertDistance.

**What do the callsigns look like? Can you spot Malaysia Airlines (MAS) and AirAsia (AXM)? Do some have trailing spaces?**  
Callsigns are 3-letter airline prefix followed by flight identifier.  
There's MAS and AXM.  
Some have trailing spaces.

**Is estDepartureAirport ever empty or odd?**.  
No, estDepartureAirport is either null or valid code. 

**What format are the time fields in?**  
Unix time in seconds, meaning the number of seconds since 1 January 1970, 00:00 UTC.  
firstSeen and lastSeen are when OpenSky's receivers first and last picked up the aircraft, which is close to, but not exactly, take-off and landing time.

**How many rows have a null estDepartureAirport? What percentage?**  
```
WITH counts AS (
	SELECT
		COUNT(*) FILTER (WHERE payload->>'estDepartureAirport' IS NULL) AS null_count,
		COUNT(*) AS total
	FROM raw.flights
)
SELECT
	null_count,
	total,
	ROUND(null_count::numeric / total * 100, 1) AS percentage
FROM counts;
```

234. 51.2%

**How many callsigns have trailing spaces? Compare the value with TRIM() of itself.**
```
SELECT count(*)
FROM raw.flights
WHERE RTRIM(payload->>'callsign') != payload->>'callsign';
```
457 (all)

**Is estArrivalAirport always WMKK?**
```
SELECT
    payload->>'estArrivalAirport' AS arrival_airport,
    COUNT(*) AS flights
FROM raw.flights
GROUP BY 1
ORDER BY 2 DESC;
```
Yes

**Which icao24s appear more than once? GROUP BY with HAVING COUNT(*) > 1.**
```
SELECT
payload->>'icao24' AS icao24,
COUNT(*)
FROM raw.flights
GROUP BY 1 
HAVING COUNT(*) > 1
ORDER BY 2 DESC
```
