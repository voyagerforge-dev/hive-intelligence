"""Re-topic the generic 'WMS reference doc' bucket (WMOS guide chapters).

Keeps the newest version of each guide (year-collapsed) and classifies each by CONTENT into one
controlled guide-topic, rewriting the `topic:` frontmatter in place. Dry-run by default.

Usage: python retopic.py [--apply] [--limit N]
"""
from __future__ import annotations
import re, sys, pathlib
sys.path.insert(0, "/home/user/Documents/github/voyagerforge-knowledge/tooling/okf-gen")
from okfgen.config import get_settings
from okfgen.llm import BifrostChat, extract_json

DOCS = pathlib.Path("/home/user/Documents/github/voyagerforge-knowledge/sources/wms-atomic/docs")
BUCKET = "WMS reference doc"

# Controlled guide-topic vocabulary. Value = what gets written to `topic:` (and becomes an AREAS key).
TOPICS = {
    "Guide: Outbound Fulfillment": "Outbound picking/packing/shipping scenarios and features: order streaming, waving, pick strategies, pack & hold, break pack, put-to-store, loading, shipping execution.",
    "Guide: Store Assortment": "Store/DC assortment and cross-dock distribution: assortment types (single/mixed/PIPO), carton consolidation (catcon), ship-to-store, ship-to-mark-for.",
    "Guide: Inventory Counting": "Inventory control and counting: cycle count, physical count/variance, lot/serial tracking, reserve movement, blocked/blind LPN, inventory adjustments.",
    "Guide: Parcel Carrier": "Small-parcel and carrier integration: FedEx, UPS, USPS, DHL, parcel-select, collate, smartlabel, manifesting, rating.",
    "Guide: Shipping Documents": "Trade/shipping paperwork and forms: bill of lading, air waybill, commercial invoice, certificate of origin, customs/NAFTA docs, shipper's letter, packing list.",
    "Guide: Retail Compliance": "Customer/retailer-specific routing and label compliance guides (e.g. named retailers/DCs) — instance-specific vendor compliance requirements.",
    "Guide: Transportation Routing": "Transportation planning, dynamic/advanced routing, appointment scheduling, load/route building, carrier selection.",
    "Guide: Labor Task": "Labor management and task execution: TLM, task-time estimation, labor standards, paper-based tasking, resource/workload.",
    "Guide: Platform Admin": "Deployment, installation, system administration, software/hardware requirements, mobile install, portlets, dashboards, e-signature.",
    "Guide: Integration": "Cross-system integration and higher-order suites: distributed order management (DOM), supply chain intelligence (SCI), extended enterprise, 3PL/billing, external systems.",
    "Guide: Reports": "Report specifications and their layouts/parameters (by item / by location / summary / detail report definitions).",
    "Guide: Yard": "Yard management scenarios: graphical yard view, dock/door, trailer/appointment yard operations.",
}

def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else None

def get_field(fm, key):
    m = re.search(rf"^{key}:\s*\"?([^\"\n]+)\"?\s*$", fm, re.M)
    return m.group(1).strip() if m else ""

def basename(stem):
    s = re.sub(r"^wms-wmos-warehouse-management-for-open-systems-", "", stem)
    return re.sub(r"^20\d\d-", "", s)

def newest_docs():
    """One path per guide base-name: the one with the highest version year."""
    best = {}
    for p in sorted(DOCS.glob("*.md")):
        fm = frontmatter(p.read_text())
        if not fm or get_field(fm, "topic") != BUCKET:
            continue
        ver = get_field(fm, "version") or "0"
        base = basename(p.stem)
        if base not in best or ver > best[base][0]:
            best[base] = (ver, p)
    return [v[1] for v in best.values()]

_SYSTEM = (
    "You classify a Manhattan WMOS guide/reference document into exactly ONE topic from the list. "
    "Base it on the document's SUBJECT, not incidental mentions. Reply ONLY {\"topic\": \"<exact topic string>\"}."
)

def classify(text, llm):
    opts = "\n".join(f"- {k}: {v}" for k, v in TOPICS.items())
    title = ""
    fm = frontmatter(text)
    if fm:
        title = get_field(fm, "title")
    body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    prompt = f"TOPICS:\n{opts}\n\nTITLE: {title}\nDOCUMENT:\n{body[:1200]}"
    data = extract_json(llm.complete(_SYSTEM, prompt) or "")
    t = (data or {}).get("topic", "")
    return t if t in TOPICS else "UNCLASSIFIED"

def set_topic(text, topic):
    return re.sub(r'^(topic:\s*).*$', f'topic: "{topic}"', text, count=1, flags=re.M)

def main():
    apply = "--apply" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    s = get_settings()
    llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.assign_model, timeout_s=s.bifrost_timeout_s)
    docs = newest_docs()
    if limit:
        docs = docs[:limit]
    from collections import Counter
    dist = Counter()
    print(f"{'topic':32} {'guide'}")
    for p in docs:
        text = p.read_text()
        topic = classify(text, llm)
        dist[topic] += 1
        print(f"{topic:32} {basename(p.stem)}")
        if apply and topic != "UNCLASSIFIED":
            p.write_text(set_topic(text, topic))
    print("\n=== distribution ===")
    for t, n in dist.most_common():
        print(f"{n:4}  {t}")
    print(f"total: {sum(dist.values())}  applied: {apply}")

if __name__ == "__main__":
    main()
