import requests

# ── MC2DP config ──────────────────────────────────────────────────────────────
MDS_URL  = "https://mc2dp.data-commons.org/mds/metadata?data=True&limit=500&offset={}"
MC2DP    = "https://mc2dp.data-commons.org/"
PREFIX   = "PREFIX/"
SKIP     = ("N/A", "mock")

# ── REMS config ───────────────────────────────────────────────────────────────
REMS_BASE    = "https://rems-qa.occ-data.org"
REMS_API_KEY = "test-urvi-occ-rems-qa"
REMS_USER    = "104799624792349711546"
LICENSE_ID   = 4
WORKFLOW_ID  = 3
FORM_ID      = 2
URN_PREFIX   = "urn:occ:mc2dp"
ORG_ID       = "Murtha Cancer Center Data Platform"

# Data sources to skip even if they have non-N/A values
SKIP_SOURCES = {"BloodPAC", "Metabolomics", "VMOAT"}

HEADERS = {
    "x-rems-api-key" : REMS_API_KEY,
    "x-rems-user-id" : REMS_USER,
    "content-type"   : "application/json",
    "accept"         : "application/json",
}

# ── MC2DP: fetch and extract ──────────────────────────────────────────────────

def fetch():
    """Pull all PREFIX/ records from MC2DP MDS in batches of 500."""
    records, offset = {}, 0
    while True:
        batch = requests.get(MDS_URL.format(offset)).json()
        if not batch: break
        records.update(batch)
        if len(batch) < 500: break
        offset += 500
    return records


def extract(records):
    """
    For each PREFIX/ key return:
      mc_id -> {description: value} for all non-N/A, non-mock crosswalk entries
    """
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


# ── REMS: existing state ──────────────────────────────────────────────────────

def get_existing_resources():
    """Return dict of resid -> resource id for all existing resources."""
    return {r["resid"]: r["id"] for r in rems_get("/api/resources")}


def get_existing_catalogue_items():
    """Return set of resource IDs that already have a catalogue item."""
    return {i["resource-id"] for i in rems_get("/api/catalogue-items")}


# ── REMS: create ──────────────────────────────────────────────────────────────

def create_resource(mc_id):
    """Create a REMS resource for a given MC ID. Returns resource id."""
    urn    = f"{URN_PREFIX}:{mc_id}"
    result = rems_post("/api/resources/create", {
        "resid"       : urn,
        "organization": {"organization/id": ORG_ID},
        "licenses"    : [LICENSE_ID],
    })
    print(f"  Created resource: {urn} → id={result['id']}")
    return result["id"]


def create_catalogue_item(mc_id, resource_id, sources):
    """
    Create a REMS catalogue item for a given MC ID.
    Data sources are embedded in the title so the governance
    committee can see which data owners to contact.
    """
    source_label = ", ".join(sorted(sources)) if sources else "Unknown"
    result = rems_post("/api/catalogue-items/create", {
        "form"        : FORM_ID,
        "resid"       : resource_id,
        "wfid"        : WORKFLOW_ID,
        "organization": {"organization/id": ORG_ID},
        "localizations": {
            "en": {
                "title"  : f"MC2DP: {mc_id} | Sources: {source_label}",
                "infourl": "https://mc2dp.data-commons.org/",
            }
        },
    })
    print(f"  Created catalogue item: {mc_id} | Sources: {source_label} → id={result['id']}")
    return result["id"]


# ── REMS: sync ────────────────────────────────────────────────────────────────

def sync_to_rems(mc_data):
    """
    For each MC ID:
      1. Create a resource if it does not already exist
      2. Create one catalogue item with data sources in the title
    """
    existing_resources       = get_existing_resources()
    existing_catalogue_items = get_existing_catalogue_items()
    created, skipped         = 0, 0

    for mc_id, crosswalk in mc_data.items():
        urn = f"{URN_PREFIX}:{mc_id}"
        print(f"\n{mc_id}")

        # create resource if it does not exist
        if urn in existing_resources:
            print(f"  Resource already exists — skipping resource creation")
            resource_id = existing_resources[urn]
            skipped += 1
        else:
            resource_id = create_resource(mc_id)
            created += 1

        # collect non-skipped data sources for this MC ID
        sources = [s for s in crosswalk.keys() if s not in SKIP_SOURCES]

        # create one catalogue item if one does not already exist
        if resource_id not in existing_catalogue_items:
            create_catalogue_item(mc_id, resource_id, sources)
        else:
            print(f"  Catalogue item already exists — skipping")

    print(f"\nDone. resources created: {created}, skipped: {skipped}")


# ── run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching MC2DP projects...")
    records = fetch()
    mc_data = extract(records)
    print(f"Found {len(mc_data)} projects\n")

    # TODO: remove slicing to run for all projects
    test_sample = dict(list(mc_data.items())[0:3])

    print("Syncing to REMS...")
    sync_to_rems(test_sample)