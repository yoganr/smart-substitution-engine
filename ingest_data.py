#!/usr/bin/env python
"""Seed / reset tool for the Smart Substitution Engine data stores.

A single self-contained script that ingests a demo catalog into **both** data
stores the system uses:

* **MongoDB Atlas** — the database owned by ``backend/SmartSubstitution.Api``
  (collections: ``products``, ``companies``, ``contracts``, ``inventory``).
  Documents are written with the *PascalCase* field names the .NET MongoDB
  driver expects (e.g. ``ProductId``, ``CategoryId``, ``IsActive``), so the
  backend deserializes them without any custom convention.
* **Milvus** — the ``product_embeddings`` vector collection used by
  ``ai-service``. The schema, embedding model (``BAAI/bge-m3``), embedding text
  (``"<name> <category_id>"``) and COSINE metric mirror
  ``ai-service/app/vectorstore.py`` exactly, so the running AI service finds a
  compatible collection and just loads it.

It is idempotent: products are upserted by ``ProductId``, vectors by ``id``.

-------------------------------------------------------------------------------
USAGE
-------------------------------------------------------------------------------
    # Ingest into both stores (default action)
    python ingest_data.py

    # Wipe everything (truncate Mongo collections + drop Milvus collection)
    python ingest_data.py --clear

    # Fresh load: clear, then ingest  (alias for --clear --ingest)
    python ingest_data.py --reset

    # Limit the scope
    python ingest_data.py --target mongo            # MongoDB only
    python ingest_data.py --clear --target milvus   # drop the vector store only

    # Skip the "are you sure?" prompt (CI / scripted runs)
    python ingest_data.py --clear --yes

    # Use your own dataset instead of the built-in demo catalog
    python ingest_data.py --data my_catalog.json

-------------------------------------------------------------------------------
DEPENDENCIES
-------------------------------------------------------------------------------
    pip install "pymongo[srv]" pymilvus sentence-transformers

(``pymilvus`` + ``sentence-transformers`` already ship with
``ai-service/requirements.txt``; ``pymongo`` is only needed for this seeder.
The first run downloads the bge-m3 model, ~2 GB, unless it is already cached.)

-------------------------------------------------------------------------------
CONFIGURATION (CLI flag overrides env var overrides default)
-------------------------------------------------------------------------------
    --mongo-uri      / MONGODB_URI    / SSE_MONGO_URI
    --db             / SSE_MONGO_DB                       (default: hackathon_db)
    --milvus-uri     / SSE_MILVUS_URI                     (default: http://localhost:19530)
    --milvus-token   / SSE_MILVUS_TOKEN                   (default: "")
    --collection     / SSE_MILVUS_COLLECTION              (default: product_embeddings)
    --embedding-model/ SSE_EMBEDDING_MODEL                (default: BAAI/bge-m3)
    --embedding-dim  / SSE_EMBEDDING_DIM                  (default: derived from model, else 1024)
    --device         / SSE_EMBEDDING_DEVICE               (default: auto; or cpu/cuda)

Credentials are never stored in this file: SSE_MONGO_URI is read from
ai-service/.env (auto-loaded) or the environment. Pass --mongo-uri to override.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Defaults (mirror ai-service/app/config.py and backend appsettings.json)
# ---------------------------------------------------------------------------
# Defaults to the LOCAL Docker MongoDB. The Atlas URI (when used) lives in
# ai-service/.env (SSE_MONGO_URI) — gitignored — which this script auto-loads.
# Override per run with --mongo-uri or the MONGODB_URI / SSE_MONGO_URI env var.
DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_DB = "hackathon_db"
DEFAULT_MILVUS_URI = "http://localhost:19530"
DEFAULT_MILVUS_TOKEN = ""
DEFAULT_COLLECTION = "product_embeddings"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_EMBEDDING_DIM = 1024

# MongoDB collection names — must match RecommendationController.cs / MongoIndexes.cs
COLL_PRODUCTS = "products"
COLL_COMPANIES = "companies"
COLL_CONTRACTS = "contracts"
COLL_INVENTORY = "inventory"
COLL_LOGS = "recommendation_logs"
MONGO_COLLECTIONS = [COLL_COMPANIES, COLL_PRODUCTS, COLL_CONTRACTS, COLL_INVENTORY, COLL_LOGS]

_VECTOR_FIELD = "vector"

# ---------------------------------------------------------------------------
# Built-in demo catalog.
#
# Defined in snake_case (the API style from HACKATHON.md). Each product carries
# its `stock_quantity`, which the seeder splits into the `inventory` collection.
# Scenario: product_001 (Chicken Breast 2kg) is OUT OF STOCK, so a replacement
# request for it from company_001 surfaces the in-stock chicken alternatives.
# ---------------------------------------------------------------------------
DEFAULT_DATASET: dict[str, list[dict[str, Any]]] = {
    "products": [
        # --- chicken ---
        {"id": "product_001", "name": "Chicken Breast 2kg", "category_id": "chicken", "brand": "Brand A", "unit": "kg", "pack_size": 2, "base_price": 10.0, "is_active": True, "dietary_tags": ["halal"], "stock_quantity": 0},
        {"id": "product_2033", "name": "Chicken Breast Premium 2kg", "category_id": "chicken", "brand": "Brand B", "unit": "kg", "pack_size": 2, "base_price": 10.5, "is_active": True, "dietary_tags": ["halal"], "stock_quantity": 150},
        {"id": "product_2099", "name": "Organic Chicken Breast 2kg", "category_id": "chicken", "brand": "Brand C", "unit": "kg", "pack_size": 2, "base_price": 11.0, "is_active": True, "dietary_tags": ["halal", "organic"], "stock_quantity": 40},
        {"id": "product_9002", "name": "Discontinued Chicken Nuggets 1kg", "category_id": "chicken", "brand": "Brand D", "unit": "kg", "pack_size": 1, "base_price": 8.0, "is_active": False, "dietary_tags": ["halal"], "stock_quantity": 0},
        # --- poultry ---
        {"id": "product_3001", "name": "Chicken Thigh Fillet 2kg", "category_id": "poultry", "brand": "Brand B", "unit": "kg", "pack_size": 2, "base_price": 9.0, "is_active": True, "dietary_tags": ["halal"], "stock_quantity": 80},
        {"id": "product_3002", "name": "Whole Chicken 1.5kg", "category_id": "poultry", "brand": "Brand A", "unit": "kg", "pack_size": 1.5, "base_price": 7.5, "is_active": True, "dietary_tags": ["halal"], "stock_quantity": 60},
        {"id": "product_3003", "name": "Turkey Breast 2kg", "category_id": "poultry", "brand": "Brand E", "unit": "kg", "pack_size": 2, "base_price": 12.0, "is_active": True, "dietary_tags": ["halal"], "stock_quantity": 30},
        # --- beef ---
        {"id": "product_4001", "name": "Beef Sirloin 2kg", "category_id": "beef", "brand": "Brand F", "unit": "kg", "pack_size": 2, "base_price": 18.0, "is_active": True, "dietary_tags": ["halal"], "stock_quantity": 25},
        {"id": "product_4002", "name": "Beef Mince 1kg", "category_id": "beef", "brand": "Brand F", "unit": "kg", "pack_size": 1, "base_price": 7.0, "is_active": True, "dietary_tags": ["halal"], "stock_quantity": 120},
        # --- pork ---
        {"id": "product_5001", "name": "Pork Loin 2kg", "category_id": "pork", "brand": "Brand G", "unit": "kg", "pack_size": 2, "base_price": 13.0, "is_active": True, "dietary_tags": [], "stock_quantity": 40},
        {"id": "product_5002", "name": "Pork Sausages 1kg", "category_id": "pork", "brand": "Brand G", "unit": "kg", "pack_size": 1, "base_price": 6.5, "is_active": True, "dietary_tags": [], "stock_quantity": 90},
        # --- fish ---
        {"id": "product_6001", "name": "Atlantic Salmon Fillet 1kg", "category_id": "fish", "brand": "Brand H", "unit": "kg", "pack_size": 1, "base_price": 16.0, "is_active": True, "dietary_tags": ["pescatarian"], "stock_quantity": 35},
        {"id": "product_6002", "name": "Cod Fillet 1kg", "category_id": "fish", "brand": "Brand H", "unit": "kg", "pack_size": 1, "base_price": 14.0, "is_active": True, "dietary_tags": ["pescatarian"], "stock_quantity": 50},
        # --- plant protein ---
        {"id": "product_7001", "name": "Tofu Firm 500g", "category_id": "plant_protein", "brand": "Brand I", "unit": "g", "pack_size": 500, "base_price": 3.0, "is_active": True, "dietary_tags": ["vegan", "gluten_free"], "stock_quantity": 200},
        {"id": "product_7002", "name": "Plant-Based Chicken Strips 500g", "category_id": "plant_protein", "brand": "Brand I", "unit": "g", "pack_size": 500, "base_price": 5.5, "is_active": True, "dietary_tags": ["vegan"], "stock_quantity": 75},
        # --- vegetables ---
        {"id": "product_8001", "name": "Fresh Carrots 5kg", "category_id": "vegetables", "brand": "Brand J", "unit": "kg", "pack_size": 5, "base_price": 4.0, "is_active": True, "dietary_tags": ["vegan", "gluten_free"], "stock_quantity": 300},
        {"id": "product_8002", "name": "Broccoli 2kg", "category_id": "vegetables", "brand": "Brand J", "unit": "kg", "pack_size": 2, "base_price": 5.0, "is_active": True, "dietary_tags": ["vegan", "gluten_free"], "stock_quantity": 110},
        # --- dairy ---
        {"id": "product_9001", "name": "Cheddar Cheese 1kg", "category_id": "dairy", "brand": "Brand K", "unit": "kg", "pack_size": 1, "base_price": 9.5, "is_active": True, "dietary_tags": ["vegetarian"], "stock_quantity": 65},
    ],
    "companies": [
        {"id": "company_001", "name": "ABC Restaurant"},
        {"id": "company_002", "name": "Gourmet Catering Co"},
    ],
    "contracts": [
        {
            "id": "contract_001",
            "company_id": "company_001",
            "items": [
                {"product_id": "product_001", "contract_price": 9.2, "is_preferred": True},
                {"product_id": "product_2033", "contract_price": 9.5, "is_preferred": False},
                {"product_id": "product_3001", "contract_price": 8.5, "is_preferred": False},
            ],
        },
        {
            "id": "contract_002",
            "company_id": "company_002",
            "items": [
                {"product_id": "product_4001", "contract_price": 17.0, "is_preferred": True},
                {"product_id": "product_6001", "contract_price": 15.5, "is_preferred": False},
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Small console helpers (ASCII only — safe on Windows cp1252 consoles)
# ---------------------------------------------------------------------------
def info(msg: str) -> None:
    print(f"[*] {msg}")


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def warn(msg: str) -> None:
    print(f"[!] {msg}")


def fail(msg: str) -> None:
    print(f"[X] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Dataset loading + mapping to store-specific shapes
# ---------------------------------------------------------------------------
def load_dataset(path: Optional[str]) -> dict[str, list[dict[str, Any]]]:
    if not path:
        return DEFAULT_DATASET
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.setdefault("products", [])
    data.setdefault("companies", [])
    data.setdefault("contracts", [])
    return data


def to_product_doc(p: dict[str, Any]) -> dict[str, Any]:
    """Map a seed product to the Mongo `products` doc (PascalCase, matched types)."""
    return {
        "ProductId": str(p["id"]),
        "Name": str(p["name"]),
        "CategoryId": str(p["category_id"]),
        "Brand": str(p.get("brand", "")),
        "Unit": str(p.get("unit", "")),
        "PackSize": float(p.get("pack_size", 0) or 0),   # C# double
        "BasePrice": float(p.get("base_price", 0) or 0),  # C# double
        "IsActive": bool(p.get("is_active", True)),
        "DietaryTags": [str(t) for t in p.get("dietary_tags", [])],
    }


def to_inventory_doc(p: dict[str, Any], now: datetime) -> dict[str, Any]:
    return {
        "ProductId": str(p["id"]),
        "StockQuantity": int(p.get("stock_quantity", 0) or 0),  # C# int
        "UpdatedAt": now,
    }


def to_company_doc(c: dict[str, Any]) -> dict[str, Any]:
    return {"CompanyId": str(c["id"]), "Name": str(c["name"])}


def to_contract_doc(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "ContractId": str(c["id"]),
        "CompanyId": str(c["company_id"]),
        "Items": [
            {
                "ProductId": str(it["product_id"]),
                "ContractPrice": float(it.get("contract_price", 0) or 0),  # C# double
                "IsPreferred": bool(it.get("is_preferred", False)),
            }
            for it in c.get("items", [])
        ],
    }


def embedding_text(name: str, category_id: str) -> str:
    """Mirror ai-service retrieval._text(): "<name> <category_id>"."""
    return " ".join(part for part in (name or "", category_id or "") if part).strip()


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------
def get_mongo_db(uri: str, db_name: str):
    try:
        from pymongo import MongoClient
    except ImportError:
        fail('pymongo is not installed. Run:  pip install "pymongo[srv]"')
        raise SystemExit(2)

    client = MongoClient(uri, serverSelectionTimeoutMS=15000, appname="sse-ingest")
    # Fail fast with a clear message if the cluster is unreachable / creds are wrong.
    client.admin.command("ping")
    return client[db_name]


def ensure_mongo_indexes(db) -> None:
    """Replicate backend/Repositories/MongoIndexes.cs (best effort)."""
    from pymongo import ASCENDING

    try:
        db[COLL_PRODUCTS].create_index([("CategoryId", ASCENDING), ("IsActive", ASCENDING)])
        db[COLL_PRODUCTS].create_index([("ProductId", ASCENDING)], unique=True)
        db[COLL_INVENTORY].create_index([("ProductId", ASCENDING)], unique=True)
        db[COLL_CONTRACTS].create_index([("CompanyId", ASCENDING)])
        ok("MongoDB indexes ensured.")
    except Exception as exc:  # non-fatal: the .NET app also ensures these on startup
        warn(f"Could not ensure all Mongo indexes: {exc}")


def clear_mongo(db) -> None:
    info(f"Truncating MongoDB collections in '{db.name}'...")
    for name in MONGO_COLLECTIONS:
        deleted = db[name].delete_many({}).deleted_count
        print(f"    - {name}: removed {deleted} document(s)")
    ok("MongoDB collections truncated.")


def ingest_mongo(db, dataset: dict) -> None:
    from pymongo import ReplaceOne

    now = datetime.now(timezone.utc)
    products = dataset.get("products", [])
    companies = dataset.get("companies", [])
    contracts = dataset.get("contracts", [])

    info(f"Ingesting into MongoDB '{db.name}'...")

    if products:
        db[COLL_PRODUCTS].bulk_write(
            [ReplaceOne({"ProductId": d["ProductId"]}, d, upsert=True)
             for d in (to_product_doc(p) for p in products)]
        )
        db[COLL_INVENTORY].bulk_write(
            [ReplaceOne({"ProductId": d["ProductId"]}, d, upsert=True)
             for d in (to_inventory_doc(p, now) for p in products)]
        )
        print(f"    - products:  upserted {len(products)}")
        print(f"    - inventory: upserted {len(products)}")

    if companies:
        db[COLL_COMPANIES].bulk_write(
            [ReplaceOne({"CompanyId": d["CompanyId"]}, d, upsert=True)
             for d in (to_company_doc(c) for c in companies)]
        )
        print(f"    - companies: upserted {len(companies)}")

    if contracts:
        db[COLL_CONTRACTS].bulk_write(
            [ReplaceOne({"ContractId": d["ContractId"]}, d, upsert=True)
             for d in (to_contract_doc(c) for c in contracts)]
        )
        print(f"    - contracts: upserted {len(contracts)}")

    ensure_mongo_indexes(db)
    ok("MongoDB ingestion complete.")


# ---------------------------------------------------------------------------
# Milvus
# ---------------------------------------------------------------------------
def get_milvus_client(uri: str, token: str):
    try:
        from pymilvus import MilvusClient
    except ImportError:
        fail("pymilvus is not installed. Run:  pip install pymilvus")
        raise SystemExit(2)

    client = MilvusClient(uri=uri, token=token)
    client.list_collections()  # force a real connection -> fail fast if Milvus is down
    return client


def ensure_milvus_collection(client, collection: str, dim: int) -> None:
    """Create the collection with the exact schema used by ai-service, or load it."""
    from pymilvus import DataType, MilvusClient

    if client.has_collection(collection):
        client.load_collection(collection)
        return

    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field(_VECTOR_FIELD, DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("name", DataType.VARCHAR, max_length=512)
    schema.add_field("category_id", DataType.VARCHAR, max_length=128)
    schema.add_field("is_active", DataType.BOOL)
    schema.add_field("dietary_tags", DataType.VARCHAR, max_length=512)

    index_params = client.prepare_index_params()
    index_params.add_index(field_name=_VECTOR_FIELD, index_type="AUTOINDEX", metric_type="COSINE")
    client.create_collection(collection_name=collection, schema=schema, index_params=index_params)
    client.load_collection(collection)
    ok(f"Created Milvus collection '{collection}' (dim={dim}).")


def clear_milvus(client, collection: str) -> None:
    info(f"Dropping Milvus collection '{collection}'...")
    if client.has_collection(collection):
        client.drop_collection(collection)
        ok(f"Dropped Milvus collection '{collection}'.")
    else:
        warn(f"Milvus collection '{collection}' did not exist; nothing to drop.")


def load_embedder(model_name: str, device: Optional[str]):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        fail("sentence-transformers is not installed. Run:  pip install sentence-transformers")
        raise SystemExit(2)

    info(f"Loading embedding model '{model_name}' (first run downloads it)...")
    model = SentenceTransformer(model_name, device=device)
    ok(f"Embedding model loaded on {model.device}.")
    return model


def ingest_milvus(client, collection: str, model, dataset: dict, dim_override: Optional[int]) -> None:
    products = dataset.get("products", [])
    if not products:
        warn("No products to index into Milvus.")
        return

    # Derive the true embedding dimension from the model (matches engine.build_engine).
    dim = dim_override
    getter = getattr(model, "get_sentence_embedding_dimension", None)
    if callable(getter):
        dim = getter() or dim
    dim = dim or DEFAULT_EMBEDDING_DIM

    ensure_milvus_collection(client, collection, dim)

    info(f"Embedding {len(products)} products with bge-m3...")
    texts = [embedding_text(p["name"], p["category_id"]) for p in products]
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).tolist()

    rows = [
        {
            "id": str(p["id"]),
            _VECTOR_FIELD: vec,
            "name": str(p["name"]),
            "category_id": str(p["category_id"]),
            "is_active": bool(p.get("is_active", True)),
            "dietary_tags": ",".join(t for t in p.get("dietary_tags", []) if t),
        }
        for p, vec in zip(products, vectors)
    ]

    info(f"Upserting {len(rows)} vectors into '{collection}'...")
    client.upsert(collection_name=collection, data=rows)
    client.flush(collection)  # make rows immediately searchable (read-after-write)

    total = 0
    try:
        total = int(client.get_collection_stats(collection).get("row_count", 0))
    except Exception:
        pass
    ok(f"Milvus ingestion complete. Collection now holds {total} row(s).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def load_dotenv() -> None:
    """Lightweight .env loader (no dependency): populate os.environ from the
    first .env found among CWD, this script's dir, and ai-service/ — without
    overwriting variables already set in the real environment."""
    here = Path(__file__).resolve().parent
    for path in (Path.cwd() / ".env", here / ".env", here / "ai-service" / ".env"):
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = val.strip().strip('"').strip("'")


def resolve(arg_val: Optional[str], *env_keys: str, default: str) -> str:
    if arg_val:
        return arg_val
    for key in env_keys:
        val = os.environ.get(key)
        if val:
            return val
    return default


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{prompt} [y/N]: ").strip().lower() in ("y", "yes")
    except EOFError:
        warn("No interactive input available; re-run with --yes to confirm.")
        return False


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed/reset MongoDB + Milvus for the Smart Substitution Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    actions = parser.add_argument_group("actions (default: --ingest)")
    actions.add_argument("--ingest", action="store_true", help="Ingest the dataset.")
    actions.add_argument("--clear", "-c", action="store_true",
                         help="Truncate Mongo collections and drop the Milvus collection.")
    actions.add_argument("--reset", action="store_true",
                         help="Clear, then ingest (alias for --clear --ingest).")

    parser.add_argument("--target", choices=["both", "mongo", "milvus"], default="both",
                        help="Which store(s) to act on (default: both).")
    parser.add_argument("--data", help="Path to a JSON dataset; defaults to the built-in demo catalog.")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt for --clear.")

    parser.add_argument("--mongo-uri", help="MongoDB connection string.")
    parser.add_argument("--db", help=f"MongoDB database name (default: {DEFAULT_DB}).")
    parser.add_argument("--milvus-uri", help=f"Milvus URI (default: {DEFAULT_MILVUS_URI}).")
    parser.add_argument("--milvus-token", help="Milvus token 'user:password' (default: none).")
    parser.add_argument("--collection", help=f"Milvus collection (default: {DEFAULT_COLLECTION}).")
    parser.add_argument("--embedding-model", help=f"Embedding model (default: {DEFAULT_EMBEDDING_MODEL}).")
    parser.add_argument("--embedding-dim", type=int, help="Embedding dim (default: derived from model).")
    parser.add_argument("--device", help="Embedding device: cpu/cuda (default: auto).")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    # Pull SSE_MONGO_URI (and friends) from a local .env if one is present.
    load_dotenv()

    # Resolve actions.
    do_clear = args.clear or args.reset
    do_ingest = args.ingest or args.reset or not do_clear  # default action is ingest
    do_mongo = args.target in ("both", "mongo")
    do_milvus = args.target in ("both", "milvus")

    # Resolve config.
    mongo_uri = resolve(
        args.mongo_uri, "MONGODB_CONNECTION_STRING", "MONGODB_URI", "SSE_MONGO_URI",
        default=DEFAULT_MONGO_URI,
    )
    db_name = resolve(args.db, "SSE_MONGO_DB", default=DEFAULT_DB)
    milvus_uri = resolve(args.milvus_uri, "SSE_MILVUS_URI", default=DEFAULT_MILVUS_URI)
    milvus_token = resolve(args.milvus_token, "SSE_MILVUS_TOKEN", default=DEFAULT_MILVUS_TOKEN)
    collection = resolve(args.collection, "SSE_MILVUS_COLLECTION", default=DEFAULT_COLLECTION)
    model_name = resolve(args.embedding_model, "SSE_EMBEDDING_MODEL", default=DEFAULT_EMBEDDING_MODEL)
    device = resolve(args.device, "SSE_EMBEDDING_DEVICE", default="") or None
    dim_override = args.embedding_dim or (
        int(os.environ["SSE_EMBEDDING_DIM"]) if os.environ.get("SSE_EMBEDDING_DIM") else None
    )

    if do_mongo and not mongo_uri:
        fail("No MongoDB URI found. Set SSE_MONGO_URI in ai-service/.env (or MONGODB_URI), "
             "or pass --mongo-uri. Use '--target milvus' to skip MongoDB.")
        return 2

    dataset = load_dataset(args.data)

    print("=" * 70)
    print("Smart Substitution Engine - data ingestion")
    print("=" * 70)
    print(f"  action(s) : {'clear ' if do_clear else ''}{'ingest' if do_ingest else ''}".strip())
    print(f"  target    : {args.target}")
    if do_mongo:
        print(f"  mongo     : {db_name}  @ {mongo_uri.split('@')[-1]}")
    if do_milvus:
        print(f"  milvus    : {collection}  @ {milvus_uri}")
    print(f"  dataset   : {args.data or 'built-in demo catalog'} "
          f"({len(dataset.get('products', []))} products, "
          f"{len(dataset.get('companies', []))} companies, "
          f"{len(dataset.get('contracts', []))} contracts)")
    print("=" * 70)

    # --- Clear -------------------------------------------------------------
    if do_clear:
        targets = []
        if do_mongo:
            targets.append(f"ALL documents in Mongo '{db_name}' ({', '.join(MONGO_COLLECTIONS)})")
        if do_milvus:
            targets.append(f"the Milvus collection '{collection}'")
        warn("About to DELETE " + " and ".join(targets) + ".")
        if not confirm("Proceed?", args.yes):
            print("Aborted.")
            return 1

        if do_mongo:
            clear_mongo(get_mongo_db(mongo_uri, db_name))
        if do_milvus:
            clear_milvus(get_milvus_client(milvus_uri, milvus_token), collection)

    # --- Ingest ------------------------------------------------------------
    if do_ingest:
        if do_mongo:
            ingest_mongo(get_mongo_db(mongo_uri, db_name), dataset)
        if do_milvus:
            client = get_milvus_client(milvus_uri, milvus_token)
            model = load_embedder(model_name, device)
            ingest_milvus(client, collection, model, dataset, dim_override)

    print("=" * 70)
    ok("Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        fail("Interrupted.")
        raise SystemExit(130)
