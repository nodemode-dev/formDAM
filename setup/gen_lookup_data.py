import gzip
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://qlever.dev/api/wikidata"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "app", "data", "lookup_world.json.gz")
PREFIX = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""
LANDMARK_RADIUS = {
    "Q570116": 1.5, "Q2319498": 1.5, "Q4989906": 1.0, "Q839954": 2.0, "Q16970": 0.5, "Q2977": 0.8, "Q44613": 1.0,
    "Q32815": 0.6, "Q44539": 0.6, "Q16560": 1.0, "Q23413": 1.5, "Q12518": 2.0, "Q1440300": 3.0, "Q11303": 2.0,
    "Q12280": 2.0, "Q12570": 3.0, "Q33506": 0.6, "Q483110": 1.0, "Q1081138": 1.5, "Q179700": 0.8, "Q174782": 0.6,
    "Q57821": 1.5, "Q24354": 0.5, "Q41176": 0.8, "Q22698": 1.5, "Q1107656": 1.0, "Q15243209": 1.5, "Q53060": 0.6,
    "Q1497364": 1.0, "Q811979": 1.0, "Q8502": 15.0, "Q8072": 15.0, "Q34038": 3.0, "Q35509": 2.0, "Q46169": 20.0,
    "Q160091": 1.0, "Q3918": 1.0, "Q1007870": 0.8, "Q207694": 0.8,
}
ART = ["Q3305213", "Q860861", "Q219423", "Q93184", "Q11060274", "Q18219090", "Q28913685"]
NOT_FOOD = {"diet", "gastronomy", "breast milk", "seed", "malt", "legume", "fast food", "Weekly Shōnen Jump", "Blue Lagoon"}
FOOD = ["Q746549", "Q2095", "Q182940", "Q41415", "Q7802", "Q10943", "Q13276", "Q477248", "Q28803", "Q9266",
        "Q40050", "Q134768", "Q1364", "Q11004", "Q3314483", "Q8274", "Q178024", "Q44", "Q8486"]
MIN_LINKS = {"landmark": 25, "art": 18, "food": 15}


def run(query: str) -> list:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": PREFIX + query})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json", "User-Agent": "DAM-build-data/1.0"})
    for attempt in range(4):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=300))
            return [{k: v["value"] for k, v in b.items()} for b in data["results"]["bindings"]]
        except (OSError, ValueError, KeyError) as exc:
            print("retry", attempt, str(exc)[:120], file=sys.stderr)
            time.sleep(10)
    raise SystemExit("query failed")


def values(ids) -> str:
    return " ".join(f"wd:{i}" for i in ids)


def landmarks() -> list:
    rows = run(f"""SELECT ?item ?label ?coord ?cls (COUNT(DISTINCT ?a) AS ?links) WHERE {{
      VALUES ?cls {{ {values(LANDMARK_RADIUS)} }}
      ?item wdt:P31 ?cls ; wdt:P625 ?coord ; rdfs:label ?label . FILTER(LANG(?label) = "en")
      ?a schema:about ?item .
    }} GROUP BY ?item ?label ?coord ?cls HAVING (COUNT(DISTINCT ?a) >= {MIN_LINKS['landmark']})""")
    best = {}
    for r in rows:
        m = re.match(r"point\(([-\d.eE]+) ([-\d.eE]+)\)", r["coord"], re.IGNORECASE)
        if not m:
            continue
        qid, cls = r["item"].rsplit("/", 1)[1], r["cls"].rsplit("/", 1)[1]
        lon, lat = float(m.group(1)), float(m.group(2))
        radius = LANDMARK_RADIUS[cls]
        prev = best.get(qid)
        if prev is None or radius > prev[3]:
            best[qid] = [r["label"], round(lat, 5), round(lon, 5), radius, int(r["links"]), qid]
    return sorted(best.values(), key=lambda x: -x[4])


def art() -> list:
    rows = run(f"""SELECT ?item ?label (SAMPLE(?cl) AS ?creator) (COUNT(DISTINCT ?a) AS ?links) WHERE {{
      VALUES ?cls {{ {values(ART)} }}
      ?item wdt:P31 ?cls ; rdfs:label ?label . FILTER(LANG(?label) = "en")
      ?a schema:about ?item .
      OPTIONAL {{ ?item wdt:P170 ?c . ?c rdfs:label ?cl . FILTER(LANG(?cl) = "en") }}
    }} GROUP BY ?item ?label HAVING (COUNT(DISTINCT ?a) >= {MIN_LINKS['art']})""")
    out = {}
    for r in rows:
        qid = r["item"].rsplit("/", 1)[1]
        out[qid] = [r["label"], r.get("creator", ""), int(r["links"]), qid]
    return sorted(out.values(), key=lambda x: -x[2])


def food() -> list:
    rows = run(f"""SELECT ?item ?label (COUNT(DISTINCT ?a) AS ?links) WHERE {{
      VALUES ?cls {{ {values(FOOD)} }}
      ?item wdt:P31|wdt:P279 ?cls ; rdfs:label ?label . FILTER(LANG(?label) = "en")
      ?a schema:about ?item .
    }} GROUP BY ?item ?label HAVING (COUNT(DISTINCT ?a) >= {MIN_LINKS['food']})""")
    out = {}
    for r in rows:
        qid = r["item"].rsplit("/", 1)[1]
        label = r["label"]
        if label in NOT_FOOD or re.search(r"\d|cuisine|list of", label, re.IGNORECASE) or len(label) > 40 or re.fullmatch(r"[A-Z][a-z]+ [a-z]+( [a-z]+)?", label):
            continue
        out[qid] = [label, int(r["links"]), qid]
    return sorted(out.values(), key=lambda x: -x[1])


def main() -> None:
    data = {"source": "Wikidata (CC0) via " + ENDPOINT, "generated": time.strftime("%Y-%m-%d"),
            "landmarks": landmarks(), "art": art(), "food": food()}
    for key in ("landmarks", "art", "food"):
        print(key, len(data[key]), file=sys.stderr)
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(data, fh, separators=(",", ":"), ensure_ascii=False)
    print("wrote", os.path.normpath(OUT), os.path.getsize(OUT), file=sys.stderr)


if __name__ == "__main__":
    main()
