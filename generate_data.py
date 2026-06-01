#!/usr/bin/env python
"""Generate and bulk-load a LARGE, VARIED catalog into MongoDB + Milvus.

Companion to ``ingest_data.py``: instead of the small fixed demo catalog, this
procedurally generates hundreds/thousands of varied products (many categories,
brands, descriptors, units, pack sizes, prices, dietary tags, stock levels),
plus companies, contracts and inventory — so the recommendation engine has a
rich, realistic dataset to work with.

It reuses ``ingest_data.py``'s connection + schema helpers, so the MongoDB
documents (PascalCase, matched to the .NET models) and Milvus vectors are
identical in shape to the demo seed — the .NET backend + ai-service consume the
generated data with no changes. Run it from the repo root:

    python generate_data.py                    # 2000 products, 50 companies -> Mongo + Milvus
    python generate_data.py --products 10000   # go bigger
    python generate_data.py --clear            # wipe everything first, then generate
    python generate_data.py --target mongo     # Mongo only (skip embeddings/Milvus)
    python generate_data.py --seed 42          # reproducible run
    python generate_data.py --products 5000 --companies 200 --batch 1000

Targets/credentials are resolved exactly like ingest_data.py
(MONGODB_CONNECTION_STRING / SSE_MILVUS_URI / SSE_EMBEDDING_MODEL ...).
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Reuse the tested connection / schema / embedding helpers from ingest_data.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_data as seed  # noqa: E402


# ---------------------------------------------------------------------------
# Variety pools — category -> (base items, baseline dietary tags, price range)
# ---------------------------------------------------------------------------
CATEGORIES: dict[str, tuple[list[str], list[str], tuple[float, float]]] = {
    "chicken":       (["Chicken Breast", "Chicken Thigh", "Chicken Wing", "Chicken Drumstick", "Whole Chicken", "Chicken Mince", "Chicken Fillet", "Chicken Tenders"], ["halal"], (6, 14)),
    "poultry":       (["Turkey Breast", "Duck Breast", "Whole Duck", "Turkey Mince", "Quail", "Goose Breast"], ["halal"], (8, 22)),
    "beef":          (["Beef Sirloin", "Beef Ribeye", "Beef Mince", "Beef Brisket", "Beef Tenderloin", "Beef Striploin", "Beef Short Rib", "Beef Rump"], ["halal"], (10, 36)),
    "pork":          (["Pork Loin", "Pork Belly", "Pork Sausages", "Pork Chop", "Pork Mince", "Bacon", "Ham Hock", "Pork Ribs"], [], (6, 18)),
    "lamb":          (["Lamb Chop", "Lamb Leg", "Lamb Shoulder", "Lamb Mince", "Lamb Rack", "Lamb Shank"], ["halal"], (12, 30)),
    "fish":          (["Atlantic Salmon Fillet", "Cod Fillet", "Tuna Steak", "Sea Bass", "Tilapia Fillet", "Mackerel", "Trout Fillet", "Haddock Fillet"], ["pescatarian"], (9, 28)),
    "seafood":       (["Shrimp", "King Prawns", "Squid Rings", "Mussels", "Scallops", "Crab Meat", "Lobster Tail", "Oysters"], ["pescatarian"], (10, 42)),
    "plant_protein": (["Tofu Firm", "Tempeh", "Plant-Based Chicken Strips", "Plant-Based Burger", "Seitan", "Plant-Based Mince", "Falafel"], ["vegan"], (3, 10)),
    "vegetables":    (["Carrots", "Broccoli", "Spinach", "Potatoes", "Onions", "Bell Peppers", "Tomatoes", "Cucumber", "Lettuce", "Cauliflower", "Zucchini", "Mushrooms", "Green Beans", "Sweet Corn"], ["vegan", "gluten_free"], (1.5, 8)),
    "fruits":        (["Apples", "Bananas", "Oranges", "Strawberries", "Grapes", "Mango", "Pineapple", "Blueberries", "Lemons", "Avocado", "Pears", "Watermelon"], ["vegan", "gluten_free"], (2, 12)),
    "dairy":         (["Cheddar Cheese", "Mozzarella", "Whole Milk", "Butter", "Greek Yogurt", "Cream", "Parmesan", "Feta Cheese"], ["vegetarian"], (3, 16)),
    "eggs":          (["Free-Range Eggs", "Organic Eggs", "Egg Whites", "Duck Eggs"], ["vegetarian"], (2.5, 8)),
    "bakery":        (["White Bread", "Whole Wheat Bread", "Baguette", "Croissant", "Bagels", "Burger Buns", "Tortilla Wraps", "Sourdough Loaf"], ["vegetarian"], (1.5, 7)),
    "grains":        (["Basmati Rice", "Jasmine Rice", "Quinoa", "Couscous", "Rolled Oats", "Brown Rice", "Bulgur Wheat"], ["vegan", "gluten_free"], (2, 12)),
    "pasta":         (["Spaghetti", "Penne", "Fusilli", "Lasagna Sheets", "Macaroni", "Tagliatelle"], ["vegetarian"], (1.5, 6)),
    "beverages":     (["Orange Juice", "Apple Juice", "Sparkling Water", "Cola", "Iced Tea", "Coffee Beans", "Green Tea", "Lemonade"], ["vegan"], (1, 20)),
    "condiments":    (["Ketchup", "Mayonnaise", "Dijon Mustard", "Soy Sauce", "Olive Oil", "Balsamic Vinegar", "Hot Sauce", "BBQ Sauce"], ["vegan"], (2, 18)),
    "frozen":        (["Frozen Peas", "Frozen Fries", "Frozen Pizza", "Vanilla Ice Cream", "Frozen Berries", "Frozen Veg Mix"], [], (2, 12)),
    "snacks":        (["Potato Chips", "Pretzels", "Mixed Nuts", "Crackers", "Popcorn", "Granola Bars"], [], (1.5, 10)),
    "deli":          (["Sliced Turkey", "Sliced Ham", "Salami", "Pastrami", "Chorizo", "Mortadella"], [], (5, 16)),
}

# unit + pack-size options by category family
_KG = ("kg", [0.5, 1, 2, 5, 10])
_G = ("g", [250, 500, 750])
_L = ("L", [0.5, 1, 2, 5])
_PCS = ("pcs", [6, 12, 24])
_DOZEN = ("dozen", [1, 2])
UNIT_BY_CATEGORY = {
    "chicken": _KG, "poultry": _KG, "beef": _KG, "pork": _KG, "lamb": _KG, "fish": _KG,
    "seafood": _KG, "deli": _G, "plant_protein": _G, "vegetables": _KG, "fruits": _KG,
    "dairy": _G, "eggs": _DOZEN, "bakery": _PCS, "grains": _KG, "pasta": _G,
    "beverages": _L, "condiments": _G, "frozen": _KG, "snacks": _G,
}

# Empty strings make "no descriptor" more common.
DESCRIPTORS = ["", "", "", "Premium", "Organic", "Fresh", "Frozen", "Free-Range",
               "Wild-Caught", "Grass-Fed", "Value", "Imported", "Local", "Extra Lean",
               "Smoked", "Marinated", "Artisan", "Halal-Certified"]
DESCRIPTOR_TAGS = {"Organic": "organic", "Free-Range": "free_range",
                   "Grass-Fed": "grass_fed", "Halal-Certified": "halal"}
PREMIUM_DESCRIPTORS = {"Premium", "Organic", "Wild-Caught", "Grass-Fed", "Artisan"}

BRANDS = ["FreshFarm", "GoldenHarvest", "PrimeCuts", "OceanCatch", "GreenLeaf", "DailyDairy",
          "SunnyFields", "ChefSelect", "Heritage", "Marina", "Verde", "Apex", "Nordic",
          "Saffron", "Highland", "Coastal", "Orchard", "Meadow", "Summit", "Riviera",
          "PureHarvest", "Bluebird", "RedBarn", "Olympus", "Tundra", "Cascade", "Verano"]

_CO_A = ["Golden", "Urban", "Royal", "Green", "Blue", "Silver", "Rustic", "Garden", "Harbor",
         "Maple", "Olive", "Saffron", "Crimson", "Coastal", "Highland", "Sunrise", "Copper"]
_CO_B = ["Fork", "Plate", "Spoon", "Table", "Kitchen", "Bistro", "Grill", "Pantry", "Hearth",
         "Skillet", "Whisk", "Platter", "Feast", "Harvest", "Cellar"]
_CO_C = ["Restaurant", "Catering", "Bistro", "Cafe", "Diner", "Eatery", "Hospitality",
         "Foods", "Group", "Canteen", "Brasserie"]


def _price(rng, lo, hi, pack, unit, premium):
    base = rng.uniform(lo, hi) * premium
    if unit in ("kg", "L"):
        base *= pack
    return round(base, 2)


def generate_products(n: int, rng: random.Random, oos_rate: float = 0.4) -> list[dict]:
    cats = list(CATEGORIES)
    out: list[dict] = []
    for i in range(n):
        cat = rng.choice(cats)
        items, base_tags, (lo, hi) = CATEGORIES[cat]
        item = rng.choice(items)
        desc = rng.choice(DESCRIPTORS)
        unit, packs = UNIT_BY_CATEGORY[cat]
        pack = rng.choice(packs)
        premium = 1.25 if desc in PREMIUM_DESCRIPTORS else 1.0
        tags = list(base_tags)
        if desc in DESCRIPTOR_TAGS and DESCRIPTOR_TAGS[desc] not in tags:
            tags.append(DESCRIPTOR_TAGS[desc])
        out.append({
            "id": f"product_{100000 + i}",
            "name": " ".join(p for p in (desc, item, f"{pack:g}{unit}") if p),
            "category_id": cat,
            "brand": rng.choice(BRANDS),
            "unit": unit,
            "pack_size": float(pack),
            "base_price": _price(rng, lo, hi, pack, unit, premium),
            "is_active": rng.random() > 0.05,            # ~5% inactive
            "dietary_tags": tags,
            "stock_quantity": 0 if rng.random() < oos_rate else rng.randint(5, 600),  # out-of-stock fraction = oos_rate
        })
    return out


def generate_companies(m: int, rng: random.Random) -> list[dict]:
    return [
        {"id": f"company_{1000 + i}",
         "name": f"{rng.choice(_CO_A)} {rng.choice(_CO_B)} {rng.choice(_CO_C)}"}
        for i in range(m)
    ]


def generate_contracts(companies: list[dict], products: list[dict], rng: random.Random) -> list[dict]:
    contracts = []
    for idx, c in enumerate(companies):
        chosen = rng.sample(products, min(rng.randint(5, 25), len(products)))
        contracts.append({
            "id": f"contract_{2000 + idx}",
            "company_id": c["id"],
            "items": [
                {"product_id": p["id"],
                 "contract_price": round(p["base_price"] * rng.uniform(0.82, 0.98), 2),
                 "is_preferred": rng.random() < 0.3}
                for p in chosen
            ],
        })
    return contracts


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# ---------------------------------------------------------------------------
# Chunked ingest (handles large counts with progress)
# ---------------------------------------------------------------------------
def bulk_ingest_mongo(db, products, companies, contracts, batch=1000) -> None:
    from pymongo import ReplaceOne

    now = datetime.now(timezone.utc)
    seed.info(f"MongoDB: upserting {len(products)} products + inventory, "
              f"{len(companies)} companies, {len(contracts)} contracts...")
    done = 0
    for chunk in _chunks(products, batch):
        db[seed.COLL_PRODUCTS].bulk_write(
            [ReplaceOne({"ProductId": d["ProductId"]}, d, upsert=True)
             for d in (seed.to_product_doc(p) for p in chunk)], ordered=False)
        db[seed.COLL_INVENTORY].bulk_write(
            [ReplaceOne({"ProductId": d["ProductId"]}, d, upsert=True)
             for d in (seed.to_inventory_doc(p, now) for p in chunk)], ordered=False)
        done += len(chunk)
        print(f"    products/inventory: {done}/{len(products)}")
    if companies:
        db[seed.COLL_COMPANIES].bulk_write(
            [ReplaceOne({"CompanyId": d["CompanyId"]}, d, upsert=True)
             for d in (seed.to_company_doc(c) for c in companies)], ordered=False)
    if contracts:
        db[seed.COLL_CONTRACTS].bulk_write(
            [ReplaceOne({"ContractId": d["ContractId"]}, d, upsert=True)
             for d in (seed.to_contract_doc(c) for c in contracts)], ordered=False)
    seed.ensure_mongo_indexes(db)
    seed.ok(f"MongoDB ingest complete (products now: {db[seed.COLL_PRODUCTS].count_documents({})}).")


def bulk_ingest_milvus(client, collection, model, products, dim_override, batch=500) -> None:
    dim = dim_override
    getter = getattr(model, "get_sentence_embedding_dimension", None)
    if callable(getter):
        dim = getter() or dim
    dim = dim or seed.DEFAULT_EMBEDDING_DIM
    seed.ensure_milvus_collection(client, collection, dim)

    seed.info(f"Milvus: embedding + upserting {len(products)} vectors (dim={dim})...")
    done = 0
    for chunk in _chunks(products, batch):
        texts = [seed.embedding_text(p["name"], p["category_id"]) for p in chunk]
        vectors = model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=64
        ).tolist()
        rows = [
            {
                "id": str(p["id"]),
                seed._VECTOR_FIELD: vec,
                "name": str(p["name"]),
                "category_id": str(p["category_id"]),
                "is_active": bool(p["is_active"]),
                "dietary_tags": ",".join(t for t in p["dietary_tags"] if t),
            }
            for p, vec in zip(chunk, vectors)
        ]
        client.upsert(collection_name=collection, data=rows)
        done += len(chunk)
        print(f"    vectors: {done}/{len(products)}")
    client.flush(collection)
    total = 0
    try:
        total = int(client.get_collection_stats(collection).get("row_count", 0))
    except Exception:
        pass
    seed.ok(f"Milvus ingest complete (collection now holds {total} rows).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate + bulk-load a large varied catalog into MongoDB + Milvus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--products", type=int, default=2000, help="How many products to generate (default 2000).")
    p.add_argument("--companies", type=int, default=50, help="How many companies to generate (default 50).")
    p.add_argument("--oos-rate", type=float, default=0.4,
                   help="Fraction of products that are OUT OF STOCK (0-1, default 0.4). Higher = more substitution demos.")
    p.add_argument("--target", choices=["both", "mongo", "milvus"], default="both")
    p.add_argument("--clear", action="store_true", help="Truncate Mongo + drop Milvus collection first.")
    p.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt for --clear.")
    p.add_argument("--seed", type=int, default=None, help="Random seed for reproducible data.")
    p.add_argument("--batch", type=int, default=500, help="Milvus embed/upsert batch size (default 500).")
    p.add_argument("--mongo-uri")
    p.add_argument("--db")
    p.add_argument("--milvus-uri")
    p.add_argument("--milvus-token")
    p.add_argument("--collection")
    p.add_argument("--embedding-model")
    p.add_argument("--embedding-dim", type=int)
    p.add_argument("--device")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    seed.load_dotenv()
    rng = random.Random(args.seed)

    do_mongo = args.target in ("both", "mongo")
    do_milvus = args.target in ("both", "milvus")

    mongo_uri = seed.resolve(args.mongo_uri, "MONGODB_CONNECTION_STRING", "MONGODB_URI",
                             "SSE_MONGO_URI", default=seed.DEFAULT_MONGO_URI)
    db_name = seed.resolve(args.db, "SSE_MONGO_DB", default=seed.DEFAULT_DB)
    milvus_uri = seed.resolve(args.milvus_uri, "SSE_MILVUS_URI", default=seed.DEFAULT_MILVUS_URI)
    milvus_token = seed.resolve(args.milvus_token, "SSE_MILVUS_TOKEN", default=seed.DEFAULT_MILVUS_TOKEN)
    collection = seed.resolve(args.collection, "SSE_MILVUS_COLLECTION", default=seed.DEFAULT_COLLECTION)
    model_name = seed.resolve(args.embedding_model, "SSE_EMBEDDING_MODEL", default=seed.DEFAULT_EMBEDDING_MODEL)
    device = seed.resolve(args.device, "SSE_EMBEDDING_DEVICE", default="") or None
    dim_override = args.embedding_dim or (
        int(os.environ["SSE_EMBEDDING_DIM"]) if os.environ.get("SSE_EMBEDDING_DIM") else None
    )

    if do_mongo and not mongo_uri:
        seed.fail("No MongoDB URI. Set MONGODB_CONNECTION_STRING in .env (or pass --mongo-uri).")
        return 2

    # --- generate ---
    seed.info(f"Generating {args.products} products + {args.companies} companies (seed={args.seed})...")
    products = generate_products(args.products, rng, args.oos_rate)
    companies = generate_companies(args.companies, rng)
    contracts = generate_contracts(companies, products, rng) if do_mongo else []
    cat_counts = Counter(p["category_id"] for p in products)
    oos = sum(1 for p in products if p["stock_quantity"] == 0)
    inactive = sum(1 for p in products if not p["is_active"])

    print("=" * 70)
    print("Bulk catalog generator")
    print("=" * 70)
    print(f"  target    : {args.target}")
    if do_mongo:
        print(f"  mongo     : {db_name} @ {mongo_uri.split('@')[-1][:45]}")
    if do_milvus:
        print(f"  milvus    : {collection} @ {milvus_uri}")
    print(f"  products  : {len(products)}  ({len(cat_counts)} categories, "
          f"{oos} out-of-stock, {inactive} inactive)")
    print(f"  companies : {len(companies)}   contracts: {len(contracts)}")
    print(f"  examples  : {products[0]['name']} | {products[len(products)//2]['name']}")
    print("=" * 70)

    # --- clear ---
    if args.clear:
        seed.warn("About to DELETE existing Mongo collections / Milvus collection.")
        if not seed.confirm("Proceed?", args.yes):
            print("Aborted.")
            return 1
        if do_mongo:
            seed.clear_mongo(seed.get_mongo_db(mongo_uri, db_name))
        if do_milvus:
            seed.clear_milvus(seed.get_milvus_client(milvus_uri, milvus_token), collection)

    # --- ingest ---
    if do_mongo:
        bulk_ingest_mongo(seed.get_mongo_db(mongo_uri, db_name), products, companies, contracts)
    if do_milvus:
        client = seed.get_milvus_client(milvus_uri, milvus_token)
        model = seed.load_embedder(model_name, device)
        bulk_ingest_milvus(client, collection, model, products, dim_override, batch=args.batch)

    print("=" * 70)
    seed.ok("Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        seed.fail("Interrupted.")
        raise SystemExit(130)
