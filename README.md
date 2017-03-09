# SMS-ModeChoice
This lays out the framework for a Python Flask web app using Twilio to allow a user to send a text message and get desired information.

Currently, there are two types of requests users can make: 

1) Best mode option

Text "Best option from ORIGIN RECOGNIZEABLE BY GOOGLE MAPS to DESTINATION"

2) Best bikeshare stations

Text "Bikeshare from ORIGIN to DESTINATION" e.g. "Bikeshare from House of Prime Rib, SF to Powell St BART"
The optimal start and end bikeshare stations with at least two available bicycles are identified. 

If you want full Google Maps directions sent by text in addition, add "with directions" to the end of the text message.

# Notes
Full web app configuration may take time, given my time commitments with other projects.

There are a couple of bugs to work out, for example, 1) Bay Area Bikeshare is the only network that seems to be working, with this web app, although the live feed for the others is included in the code; 2) getting the Lyft API to work with input coordinates as well as destination names (e.g. "House of Prime Rib, SF"). As-is, this web app does work and is currently set up with pythonanywhere.com. More details will be posted here pending future improvements to the interface. 
