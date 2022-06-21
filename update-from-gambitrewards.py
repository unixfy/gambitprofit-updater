import json
import os
import re
import requests

# # Debug logging
# http.client.HTTPConnection.debuglevel = 1
# logging.basicConfig()
# logging.getLogger().setLevel(logging.DEBUG)
# req_log = logging.getLogger('requests.packages.urllib3')
# req_log.setLevel(logging.DEBUG)
# req_log.propagate = True

#################### DEFINE VARIABLES HERE! ####################
# Gambit Rewards JWT token endpoint
LOGIN_URL = "https://api-production.gambitrewards.com/api/v1/user/login/"
# Gambit Rewards general matches endpoint
MATCHES_ENDPOINT = "https://api-production.gambitrewards.com/api/v1/matches/"
# Gambit Rewards credentials
USERNAME = os.environ['GAMBIT_USERNAME']
PASSWORD = os.environ['GAMBIT_PASSWORD']

# API endpoint
API_ENDPOINT = "https://api.gambitprofit.com/"
# API backend credentials
API_USERNAME = os.environ['API_USERNAME']
API_PASSWORD = os.environ['API_PASSWORD']


#################################################################

def getMatches():
    """
    Function to log into GambitRewards and fetch the latest games and return them in a list
    :return:
    """
    # Log into Gambit Rewards
    gambitrewards_auth = requests.post(LOGIN_URL, json={"auth": {"email": USERNAME, "password": PASSWORD}}).json()

    print("Logged in to GambitRewards")

    # Fetch JWT from the login request
    gambitrewards_jwt = gambitrewards_auth["jwt"]

    # Grab all the matches from Gambit
    matches = requests.get(MATCHES_ENDPOINT, headers={"Authorization": gambitrewards_jwt}).json()
    print(f"Matches response from GambitRewards: {str(matches)}")

    print("Adding all items to games dict")
    games = {}
    for item in matches["items"]:
        games[item["id"]] = {"name": item["name"], "datetime": item["datetime"]}

    print("Iterating through games dict to get the attributes we need")
    # id = each game's ID
    # deets = all of the details (i.e. the values dictionary in the k,v pair in the games
    # dict consisting of name, datetime)
    for id, deets in games.items():
        # Build the URL that will give us the details for each game
        match_api_url = MATCHES_ENDPOINT + id

        # Fire off a GET request to the previously generated URL to get details on the game
        # Then parse as JSON
        game_spec = requests.get(match_api_url, headers={"Authorization": gambitrewards_jwt})
        game_spec_response = game_spec.json()

        # Only consider games with 3 or less teams (so we don't end up with nascar, golf etc games)
        if len(game_spec_response["item"]["bet_types_matches"][0]["match_lines"]) <= 3:
            # Loop through all of the bet types matches in the API response
            # until we find one where the label is pick the winner
            for bet_types_match in game_spec_response["item"]["bet_types_matches"]:
                if bet_types_match["bet_type"]["label"] == "Pick the Winner":
                    # Add the team name and payout for the first 2 teams
                    deets["ptw"] = [
                        {
                            "description": bet_types_match["match_lines"][0]["description"],
                            "payout": bet_types_match["match_lines"][0]["payout"]
                        },
                        {
                            "description": bet_types_match["match_lines"][1]["description"],
                            "payout": bet_types_match["match_lines"][1]["payout"]
                        }
                    ]

                    # Also try to grab the name and payout for the third team (usually draw)
                    # However, this doesn't always exist so I need to make sure to catch
                    # any exceptions that can occur here
                    try:
                        deets["ptw"].append(
                            {
                                "description": bet_types_match["match_lines"][2]["description"],
                                "payout": bet_types_match["match_lines"][2]["payout"]
                            }
                        )
                    except IndexError:
                        pass
        else:
            # Temporarily blacklist games with more than 3 teams
            blacklist.append(id)

    return games


def update(key, value, payload_upd):
    """
    Function to create a list of items to be updated in our API
    :param key:
    The UUID-like string at the end of each play URL
    :param value:
    The various attributes associated with the play
    :param payload_upd:
    An existing payload to append to
    :return:
    """
    PlayDate = value["datetime"][0:19] + value["datetime"][23:]

    # All of this data needs to be appended regardless of whether there is a draw or not
    current_game =  {
            "Calc": {
                "HighRisk": {},
                "MedRisk": {},
                "NoRisk": {}
            },
            "PlayDate": PlayDate,
            "PlayUrl": "https://app.gambitrewards.com/match/" + key,
            "Team1": {
                "Name": value["ptw"][0]["description"],
                "Reward": float(value["ptw"][0]["payout"])
            },
            "Team2": {
                "Name": value["ptw"][1]["description"],
                "Reward": float(value["ptw"][1]["payout"])
            }
        }

    # Handle games with a draw (3rd team)
    if len(value["ptw"]) == 3:
        counter = -1
        for item in value["ptw"]:
            counter += 1
            if item["description"] == "Draw":
                break

        draw_reward = value["ptw"][counter]
        value["ptw"].pop(counter)

        current_game["Draw"] = {
            "Reward": float(draw_reward["payout"])
        }

    # Handle games without a draw (only 2 teams)
    # In this case, we just append an empty Draw dict to prevent mongo errors
    else:
        current_game["Draw"] = {}

    payload_upd.append(current_game)

    return payload_upd


def cleanUp():
    """
    Function that takes our list of plays to create/update and submits them as http requests to our API
    :return:
    """
    games = getMatches()
    print("Creating payload: Stage 3")
    print("Games pulled from GambitRewards: " + str(games))

    # Games to be created
    payload = []
    # Games to be updated
    payload_upd = []
    # IDs to be updated
    ids_upd = []

    # Iterate through all games
    for key, value in games.items():
        # Break the loop if the ptw value doesn't exist
        try:
            print(len(value["ptw"]))
        except KeyError:
            continue

        checkdupe = requests.get(f"{API_ENDPOINT}gambit-plays?PlayUrl=https://app.gambitrewards.com/match/{key}")
        # If the API says this game already exists, append it to the update queue
        # and don't append it to the create queue
        if checkdupe.json():
            payload_upd = update(key, value, payload_upd)
            ids_upd.append(checkdupe.json()[0]["_id"])
            continue

        PlayDate = value["datetime"][0:19] + value["datetime"][23:]

        # All of this data needs to be appended regardless of whether there is a draw or not
        current_game = {
            "Calc": {
                "HighRisk": {},
                "MedRisk": {},
                "NoRisk": {}
            },
            "PlayDate": PlayDate,
            "PlayUrl": "https://app.gambitrewards.com/match/" + key,
            "Team1": {
                "Name": value["ptw"][0]["description"],
                "Reward": float(value["ptw"][0]["payout"])
            },
            "Team2": {
                "Name": value["ptw"][1]["description"],
                "Reward": float(value["ptw"][1]["payout"])
            }
        }

        # Handle games with a draw
        if len(value["ptw"]) == 3:
            counter = -1
            for item in value["ptw"]:
                counter += 1
                if item["description"] == "Draw":
                    break

            draw_reward = value["ptw"][counter]
            value["ptw"].pop(counter)

            current_game["Draw"] = {
                "Reward": float(draw_reward["payout"])
            }

        # Handle games without a draw
        else:
            current_game["Draw"] = {}

        payload.append(current_game)

    return payload, payload_upd, ids_upd


# List of plays that should not be updated or created...
# This game has some weird negative numbers for odds
blacklist = ['https://app.gambitrewards.com/match/7ae8da6a-5d5f-4fd9-a1f3-4fe40f0dde8e']

# Get all our data from the cleanup() function
payload, payload_upd, ids_upd = cleanUp()

# Sign into API backend
api_auth = requests.post(f"{API_ENDPOINT}auth/local",
                         json={"identifier": API_USERNAME, "password": API_PASSWORD}).json()

# Fetch JWT from GambitProfit API
api_jwt = api_auth["jwt"]

print("Successfully logged into API backend")

for item in payload:
    if item["PlayUrl"] not in blacklist:
        api_post = requests.post(f"{API_ENDPOINT}gambit-plays", json=item,
                                 headers={"Authorization": f"Bearer {api_jwt}"})

        print(api_post.text)

# The counter helps iterate through the IDs that need to be updated
# Yeah, this is really shitty solution but it works :shrug:
counter = 0
for item in payload_upd:
    if item["PlayUrl"] not in blacklist:
        api_put = requests.put(f"{API_ENDPOINT}gambit-plays/{ids_upd[counter]}", json=item,
                               headers={"Authorization": f"Bearer {api_jwt}"})
        counter += 1
        print(api_put.text)

print("Script ending")
