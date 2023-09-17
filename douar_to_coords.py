import concurrent
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from textwrap import dedent
import googlemaps
import pandas as pd
from geopy.distance import distance as geo_distance
from tqdm.notebook import tqdm


def api_key():
    if "GOOGLE_MAPS_API_KEY" in os.environ:
        return os.environ["GOOGLE_MAPS_API_KEY"]

    api_key_file = Path(__file__).parent / "google_maps_api.key"
    if api_key_file.exists():
        with api_key_file.open("r") as f:
            return f.read().strip()

    raise ValueError(
        dedent(
            """No Google Maps API key found. Please set it in the environment variable
        GOOGLE_MAPS_API_KEY or in a file named google_maps_api.key in the same
        directory as this script."""
        )
    )


def summarize(candidates):
    """
    Print a summary of all the candidate results by the Google Maps API
    to debug / improve the matching method (`geocode_filter`)

    Args:
        candidates (list[dict]): List of candidate Google Maps results to summarize
    """

    print(f"\nNumber of candidates: {len(candidates)}\n\n----\n")

    for cand in candidates:
        print(
            "• Components:\n  "
            + ", ".join(
                f'{c["long_name"]} ({", ".join(c["types"])})'
                for c in cand["address_components"]
            )
        )
        print("• Formatted address:\n  " + cand["formatted_address"])
        print(
            "• GPS:\n "
            + f'{cand["geometry"]["location"]["lat"]}, {cand["geometry"]["location"]["lng"]}'
        )
        print("\n----\n")
    for c, cand1 in enumerate(candidates):
        for j in range(c):
            cand2 = r[j]
            dist = geo_distance(
                (
                    cand1["geometry"]["location"]["lat"],
                    cand1["geometry"]["location"]["lng"],
                ),
                (
                    cand2["geometry"]["location"]["lat"],
                    cand2["geometry"]["location"]["lng"],
                ),
            )
            print(f"Direct distance {j}<>{c} : {dist.km:.2f}km")


def parallel_map(f, my_iter, results, workers=5):
    """
    Map the function f over the iterable my_iter using multiple threads (workers).
    Results of the computation are sored in results which should be a dict as:

    ```
    for item in my_iter:
        results[item] = f(item)
    ```

    In particular, item should be hashable (typically an int or a str).

    Args:
        f (callable): Funciton to map to the iterable
        my_iter (iterable): Iterable to map the function to
        results (dict): Data structure to store the results into
        workers (int, optional): Number of workers for parallel (threads) mapping.
            will not use threads if workers <= 1. Defaults to 5.
    """

    if workers < 2:
        return [f(i) for i in tqdm(my_iter)]
    l = len(my_iter)
    with tqdm(total=l) as pbar:
        # let's give it some more threads:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(f, arg): arg for arg in my_iter}
            for future in concurrent.futures.as_completed(futures):
                arg = futures[future]
                results[arg] = future.result()
                pbar.update(1)


def geocode_filter(address):
    """
    Query the Google Maps API and selects the best results.

    Args:
        address (str): `{index}--{address}` where index is the index of the address
            in the original dataframe

    Returns:
        list[dict]: List of selected Google Maps results
    """
    # query Google Maps
    address = address.split("--")[-1]
    geocodes = gmaps.geocode(address)

    # split address
    parts = address.split(", ")
    parts = parts[0].split(" ") + parts[1:]
    # store address parts as a dict: part -> index_in_parts
    # for instance: parts["Casablanca"] -> 0 in 'Casablaca, Morocco'
    parts = {a: i for i, a in enumerate(parts)}

    # Find the best match: the lower the rank, the more precise the result
    # so we look for the lowest rank assuming the more precise result.
    ranks = []
    for gc in geocodes:
        ranks.append(
            min(
                [
                    min(
                        [
                            parts.get(c["short_name"], len(parts)),
                            parts.get(c["long_name"], len(parts)),
                        ]
                    )  # find earliest index in the address for this address component
                    for c in gc["address_components"]
                    if "plus_code" not in c["types"]
                ]
            )
        )  # find earliest index in the address across address components

    # find Google Maps result with minimal rank
    min_rank = min(ranks)

    # select all results with minimal rank (hopefully only one)
    selected_codes = [geocodes[k] for k, r in enumerate(ranks) if r == min_rank]
    if len(selected_codes) == 1:
        return selected_codes

    # more than 1 results have the same lowest rank

    # compute distances ; if the distance between all results is <1km, assume it's the same place
    lat_longs = [
        (gc["geometry"]["location"]["lat"], gc["geometry"]["location"]["lng"])
        for gc in selected_codes
    ]
    if all(geo_distance(ll1, ll2).km < 1 for ll1 in lat_longs for ll2 in lat_longs):
        return selected_codes[:1]

    # distances are larger than 1km

    # favour the results with a "locality" entry, even if they have the same lowest rank
    candidate_codes = [
        gc
        for gc in selected_codes
        if any("locality" in c["types"] for c in gc["address_components"])
    ]

    if candidate_codes:
        # candidate codes could be empty at this point
        selected_codes = candidate_codes

    # count total address components
    n_matches = [len(gc["address_components"]) for gc in selected_codes]
    max_matches = max(n_matches)
    # assume more components <=> more precision => prefer those ones
    selected_codes = [
        selected_codes[k] for k, m in enumerate(n_matches) if m == max_matches
    ]

    # if for some reason there is not item in selected_codes,
    # default to returning the initial results
    return selected_codes or geocodes


def debug(results, stop_iter, n_matches_target, print_raw=False):
    """
    Debugging function to print the results of the Google Maps API query
    according to the `stop_iter` and `n_matches_target` parameters:
    it will summarize the results of the `stop_iter`-th item with `n_matches_target`
    candidates.

    Args:
        results (list[dict]): List of Google Maps candidate results
        stop_iter (int): Index of the item to summarize in its category of number of
            results
        n_matches_target (int): Category of number of results to summarize (e.g. 3).
    """

    # Print the address query and a summary of the matched results.
    stop_iter = 5
    n_matches_target = 3
    # Print summary for the `stop_iter`-th item with `n_matches_target` candidates
    n_with_target = 0
    for a, r in results.items():
        if len(r) == n_matches_target:
            n_with_target += 1
        if n_with_target >= stop_iter:
            break
    print(a)
    summarize(r)

    if print_raw:
        print("\n----\n")
        print(results)


if __name__ == "__main__":
    file_name = "listes-localités.xlsx"

    assert Path(file_name).exists(), f"File {file_name} not found"

    df = pd.read_excel("listes-localités.xlsx")
    gmaps = googlemaps.Client(key="AIzaSyBgUEGITwWtnyeMgfBIBYQHrPaXwPDmZgI")

    # Transform the dataframe columns in a single Google Maps query
    df["query"] = df.apply(
        lambda x: f"{x.name}--{x['nom_fr']} {x['nom_ar']}, {x['commune_fr']}, {x['cercle_fr']}, {x['province_fr']}, {x['region_fr']}, Morocco",
        axis=1,
    )
    # Query and fitler Google Maps
    results = {}
    parallel_map(geocode_filter, df["query"].values, results, workers=10)

    # Analyse results
    counter = Counter([len(r) for r in results.values()])
    matches = sorted(counter.keys())
    for m in matches:
        print(f"Number of addresses with {m} matches: {counter[m]}")

    results_list = sorted(results.items(), key=lambda r: int(r[0].split("--")[0]))
    results_list = [r[1] for r in results_list]
    gps_locs = [
        " | ".join(
            f"({r['geometry']['location']['lat']:.7f}, {r['geometry']['location']['lng']:.7f})"
            for r in candidates
        )
        for candidates in results_list
    ]

    df["Google Maps query"] = df["query"].apply(lambda x: x.split("--")[-1])
    df = df.drop(columns=["query"])
    df["gps"] = gps_locs

    df.to_excel(Path(file_name).stem + "-gps" + Path(file_name).suffix, index=False)
