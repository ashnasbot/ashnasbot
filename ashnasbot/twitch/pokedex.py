import json
import logging
import os
import time

from . import db


def get_pokemon(num_or_name):
    tbl_name = "pokedex"
    try:
        if not db.exists(tbl_name):
            db.create(tbl_name, primary="name")
            dir_path = os.path.dirname(os.path.realpath(__file__))
            pokedex_path = os.path.join(dir_path, "data", "pokedex.json")
            with open(pokedex_path, 'r', encoding="utf8") as f:
                pokedata = json.load(f)
                pokedex = []

                for entry in pokedata:
                    pokedex.append({
                        "id": entry["id"],
                        "name": entry["name"],
                        "found_in": entry["found_in"],
                        "dex_entry": " ".join(entry["dex_entry"].split()),
                        "caughtby": "{}"
                    })

                db.update_multi(tbl_name, pokedex, primary="name", keys=["id", "name", "caughtby", "found_in", "dex_entry"])
    except Exception as e:
        print("Err", e)

    tbl = db.get(tbl_name)
    try: 
        num = int(num_or_name)
        return next((p for p in tbl if p["id"] == num), None)
    except ValueError:
        return next((p for p in tbl if p["name"].lower() == num_or_name.lower()), None)
    except Exception as e:
        print(e)

    return None

def get_player_pokedex(name):
    tbl_name = name + "_pokedex"
    try:
        if not db.exists(tbl_name):
            db.create(tbl_name, primary="id")
            dir_path = os.path.dirname(os.path.realpath(__file__))
            pokedex_path = os.path.join(dir_path, "data", "pokedex.json")
            with open(pokedex_path, 'r', encoding="utf8") as f:
                pokedata = json.load(f)
                pokedex = []

                for entry in pokedata:
                    pokedex.append({
                        "id": entry["id"],
                        "caught": False,
                        "when": None
                    })

                db.update_multi(tbl_name, pokedex, primary="name", keys=["id", "caught", "when"])
    except Exception as e:
        print("Err", e)

    return db.get(tbl_name)


def player_pokedex_catch(name, num, caught=True):
    tbl_name = name + "_pokedex"
    row = dict(id=num, caught=caught)
    db.update(tbl_name, row, ['id'])
