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