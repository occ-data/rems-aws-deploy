import requests

# ── MC2DP config ──────────────────────────────────────────────────────────────
MDS_URL  = "https://mc2dp.data-commons.org/mds/metadata?data=True&limit=500&offset={}"
MC2DP    = "https://mc2dp.data-commons.org/"
PREFIX   = "PREFIX/"
SKIP     = ("N/A", "mock")

# ── REMS config ───────────────────────────────────────────────────────────────
REMS_BASE    = "https://rems-qa.occ-data.org"
REMS_API_KEY = "test-urvi-occ-rems-qa"
REMS_USER = "104799624792349711546"
LICENSE_ID   = 1   # e.g. 1
WORKFLOW_ID  = 1   # e.g. 1
FORM_ID      = 1   # e.g. 1
URN_PREFIX   = "urn:occ:mc2dp"
ORG_ID = "Murtha Cancer Center Data Platform"

HEADERS = {
    "x-rems-api-key" : REMS_API_KEY,
    "x-rems-user-id" : REMS_USER,
    "content-type"   : "application/json",
    "accept"         : "application/json",
}

# ── MC2DP: fetch and extract ──────────────────────────────────────────────────

def fetch():
    records, offset = {}, 0
    while True:
        batch = requests.get(MDS_URL.format(offset)).json()
        if not batch: break
        records.update(batch)
        if len(batch) < 500: break
        offset += 500
    return records

def extract(records):
    out = {}
    for key, rec in records.items():
        if not key.startswith(PREFIX): continue
        subject = rec.get("crosswalk", {}).get("subject", {})
        mc = next(iter(subject.get(MC2DP, {}).values()), {}).get("value", "")
        if not mc or mc.startswith(SKIP): continue
        out[mc] = {
            v.get("description", k): v.get("value")
            for k, fields in subject.items()
            if k not in (MC2DP, "mapping_methodologies") and isinstance(fields, dict)
            for v in fields.values()
            if isinstance(v, dict) and not v.get("value", "").startswith(SKIP)
        }
    return out

# ── REMS: helpers ─────────────────────────────────────────────────────────────

def rems_get(path):
    r = requests.get(f"{REMS_BASE}{path}", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def rems_post(path, body):
    r = requests.post(f"{REMS_BASE}{path}", headers=HEADERS, json=body)
    if not r.ok:
        print(f"  Error {r.status_code}: {r.text}")
    r.raise_for_status()
    return r.json()

# ── REMS: create ──────────────────────────────────────────────────────────────

def get_existing_resources():
    return {r["resid"] for r in rems_get("/api/resources")}

def get_existing_catalogue_items():
    return {i["resource-id"] for i in rems_get("/api/catalogue-items")}

def create_resource(mc_id):
    urn    = f"{URN_PREFIX}:{mc_id}"
    result = rems_post("/api/resources/create", {
        "resid"       : urn,
        "organization": {"organization/id": ORG_ID},
        "licenses"    : [LICENSE_ID],
    })
    print(f"  Created resource: {urn} → id={result['id']}")
    return result["id"]

def create_catalogue_item(mc_id, resource_id):
    result = rems_post("/api/catalogue-items/create", {
        "form"        : FORM_ID,
        "resid"       : resource_id,
        "wfid"        : WORKFLOW_ID,
        "organization": {"organization/id": ORG_ID},
        "localizations": {
            "en": {
                "title"  : f"MC2DP id: {mc_id}",
                "infourl": "https://mc2dp.data-commons.org/",
            }
        },
    })
    print(f"  Created catalogue item: MC2DP id {mc_id} → id={result['id']}")
    return result["id"]

# ── REMS: sync ────────────────────────────────────────────────────────────────

def sync_to_rems(mc_ids):
    existing_resources       = get_existing_resources()
    existing_catalogue_items = get_existing_catalogue_items()
    created, skipped         = 0, 0

    for mc_id in mc_ids:
        urn = f"{URN_PREFIX}:{mc_id}"
        print(f"\n{mc_id}")
        if urn in existing_resources:
            print(f"  Skipping. already exists")
            skipped += 1
            continue
        resource_id = create_resource(mc_id)
        if resource_id not in existing_catalogue_items:
            create_catalogue_item(mc_id, resource_id)
        created += 1

    print(f"\nDone. created: {created}, skipped: {skipped}")

# ── run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching MC2DP projects...")
    mc_ids = list(extract(fetch()).keys())
    print(f"Found {len(mc_ids)} projects\n")
    print("Syncing to REMS...")
    mc_ids = ["MC-CE40CF", "MC-57ED9B"]
    sync_to_rems(mc_ids)