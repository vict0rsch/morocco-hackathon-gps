# morocco-hackathon-gps

Assign GPS locations to 7000 villages in Morocco

This work was done in the context of [the Morocco Solidarity Hackathon](https://morocco-solidarity-hackathon.io/).

## How to use

1. Install requirements

   ```bash
   pip install -r requirements.txt
   ```

2. Get a Google Maps API key
   1. Store it in the untracked file `./google_maps_api.key`
   2. Or as an environment variable `GOOGLE_MAPS_API_KEY=<your key>`

3. Run the script

   ```bash
   $ python douar_to_coords.py
   Writing to ./listes-localités-gps.xlsx
   ```
