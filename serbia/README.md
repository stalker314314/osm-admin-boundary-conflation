This folder contains set of scripts to aid daily checks of OSM admin boundaries in Serbia against official cadastre data.
All scripts here are very much specific to Serbia and not of interest for other readers. Do check how it all works end to end.

All of this is done by using local overpass server and doing couple of steps:
* Initialize data from yesterday (PBF data) to serve as a baseline and calculate statistics
* Update cadastre data from today and calculate statistics again, finding differences that are due to cadastre changes
* Update today's OSM data and calculate statistics again, finding differences that are due to OSM changes

If there are any changes (either cadastre or OSM) that are worse than yesterday, shoot Telegram message.

Start with `measurement.sh` script to dive in.