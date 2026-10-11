"""Create the protocol inputs. Do not regenerate a manifest to improve measured results."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def guid(group, index):
    return f"{group:08X}{index:08X}0000000000000001"


def graph(group, family, count, seed, locked=False):
    rooms = []
    square = [[0, 0], [1400, 0], [1400, 1400], [0, 1400]]
    for i in range(count):
        rooms.append(dict(id=guid(group, i + 1), name=f"Room {i + 1}",
                          type=0, role=1 if i == 0 else (2 if i == (2 if locked else count - 1) else 0),
                          locked=locked, position=square[i] if locked else [0, 0],
                          width=600, depth=600))
    if family == "branching":
        edges = [((i - 1) // 2, i) for i in range(1, count)]
    else:
        edges = [(i, i + 1) for i in range(count - 1)]
        if family == "ring":
            edges.append((count - 1, 0))
    connections = [dict(id=guid(group, 100 + i), a=rooms[a]["id"], b=rooms[b]["id"],
                        corridor_width=200, door_width=150,
                        door_a=dict(manual=False, side=1, offset=300),
                        door_b=dict(manual=False, side=1, offset=300))
                   for i, (a, b) in enumerate(edges)]
    return dict(seed=seed, schema_version=1, start=rooms[0]["id"],
                goal=rooms[2 if locked else count - 1]["id"], rooms=rooms, connections=connections)


def main():
    cases = []
    for f, family in enumerate(["chain", "branching", "ring"]):
        for i, count in enumerate([5, 10, 20, 5, 10, 20, 5, 10, 20, 5]):
            case_graph = graph(100 + f * 10 + i, family, count, 17001 + f * 1000 + i * 97)
            # The current placement implementation does not consume Seed. Vary real
            # dimensions as well: repeated room counts must not just relabel geometry.
            for room_index, room in enumerate(case_graph["rooms"]):
                room["width"] = 600 + 50 * i + 50 * (room_index % 3)
                room["depth"] = 600 + 50 * ((room_index + i + 2 * f) % 4)
            cases.append(dict(id=f"{family}-{i + 1:02}", family=family, graph=case_graph))
    base = graph(500, "ring", 4, 12345, locked=True)
    names = ["hub-material", "display-name", "room-width", "room-depth", "room-position",
             "door-width", "corridor-width", "remove-connection", "remove-room", "array-order"]
    benchmarks = []
    for i, name in enumerate(names):
        edit = copy.deepcopy(base)
        if i == 0: edit["rooms"][1]["type"] = 1
        elif i == 1: edit["rooms"][1]["name"] = "Renamed Room"
        elif i == 2: edit["rooms"][0]["width"] = 650
        elif i == 3: edit["rooms"][1]["depth"] = 650
        elif i == 4: edit["rooms"][3]["position"][0] -= 50
        elif i == 5: edit["connections"][0]["door_width"] = 200
        elif i == 6: edit["connections"][0]["corridor_width"] = 250
        elif i == 7: edit["connections"].pop()
        elif i == 8:
            edit["rooms"].pop()
            edit["connections"] = edit["connections"][:2]
        elif i == 9:
            edit["rooms"][0], edit["rooms"][3] = edit["rooms"][3], edit["rooms"][0]
            edit["connections"][0], edit["connections"][3] = edit["connections"][3], edit["connections"][0]
        benchmarks.append(dict(id=name, baseline=copy.deepcopy(base), edited=edit))
    manifest = dict(protocol_version=1, input_set_version=2, input_set_name="varied-dimensions",
                    algorithm_version="PlayableSketch-pipeline-v1",
                    warmups=1, repetitions=5,
                    settings=dict(grid_cm=50, room_gap_cm=400, max_placement_attempts=128,
                                  wall_height_cm=300, wall_thickness_cm=20, door_height_cm=220,
                                  corner_margin_cm=50, floor_thickness_cm=20,
                                  min_corridor_width_cm=100, agent_radius_cm=40,
                                  agent_height_cm=180, clearance_cm=10,
                                  navigation_max_cells=250000, navigation_max_work=50000000),
                    cases=cases, benchmarks=benchmarks)
    target = ROOT / "Experiments" / "manifest.json"
    target.parent.mkdir(exist_ok=True)
    data = (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode()
    target.write_bytes(data)
    target.with_suffix(".sha256").write_text(hashlib.sha256(data).hexdigest() + "\n", encoding="ascii")
    print(f"Fixed {len(cases)} generation cases and {len(benchmarks)} edit pairs.")


if __name__ == "__main__":
    main()
