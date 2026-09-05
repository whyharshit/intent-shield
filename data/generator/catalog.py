"""Build the Warrant product catalog from real Indian retail sources.

Every SKU here is a real product with a real price. Nothing is invented. The
sources, all in data/raw/:

  bigbasket.csv          8,208  grocery, produce, staples, personal care, household
  karnataka_liquor.csv   8,180  alcohol, scraped from the Karnataka excise price list
  Fashion Dataset v2.csv 14,214 women's apparel (Myntra)
  flipkart_*.csv          2,460 electronics
  A_Z_medicines...csv   253,000 pharmacy
  swiggy_sample.csv      60,000 restaurant menu items

Source categories are mapped onto the taxonomy by ordered regex rules. This is
a build-time join — deterministic, inspectable, no embeddings and no model. The
embedding mapper in C4 is for *cart line items at verification time*, where the
merchant's category string is untrusted or absent. Using one here would make
the catalog's own labels probabilistic, and those labels are the ground truth
the eval grades against.

Rows that match no rule are dropped, not guessed at. `--report` prints the drop
rate per source; it is a quality signal, not something to suppress.

Usage:
    python data/generator/catalog.py --build
    python data/generator/catalog.py --report
    python data/generator/catalog.py --sample 15
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel, ConfigDict, Field, field_validator

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from warrant.taxonomy import Taxonomy, default_taxonomy  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "catalog" / "catalog.jsonl"

DEFAULT_SEED = 1337
TARGET_SIZE = 800

# How many SKUs of each taxonomy root end up in the catalog.
#
# Not proportional to the sources. BigBasket is 46% cosmetics and 1.4% fresh
# produce, which is upside-down for a weekly-groceries mandate — the domain the
# demo lives in. These quotas rebalance toward that world while keeping enough
# alcohol, apparel, electronics and pharma for violations to be injected into.
QUOTAS: dict[str, int] = {
    "grocery": 150,
    "staples": 115,
    "alcohol": 115,
    "personal_care": 95,
    "apparel": 75,
    "household": 65,
    "produce": 55,
    "electronics": 50,
    "pharma": 45,
    "restaurant": 35,
}


class CatalogItem(BaseModel):
    """One real product, normalised across sources."""

    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    brand: str | None = None
    category: str = Field(min_length=1)  # taxonomy leaf id
    root: str = ""  # derived from `category` by collect(); loaders leave it blank
    attributes: dict[str, str] = Field(default_factory=dict)
    price_paise: int = Field(gt=0)
    source: str = Field(min_length=1)
    source_ref: str | None = None

    @field_validator("title")
    @classmethod
    def _tidy(cls, v: str) -> str:
        return re.sub(r"\s+", " ", v).strip()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _paise(rupees: str | float | int | None) -> int | None:
    """Rupees (any of the messy shapes the sources use) -> integer paise."""
    if rupees is None:
        return None
    s = str(rupees).strip()
    if not s:
        return None
    s = s.replace("₹", "").replace(",", "").replace("Rs.", "").replace("Rs", "")
    s = s.strip()
    try:
        val = float(s)
    except ValueError:
        return None
    if val <= 0:
        return None
    return int(round(val * 100))


def _first_match(signal: str, rules: list[tuple[str, str]]) -> str | None:
    """Ordered rules; first hit wins. Order is the whole design here."""
    for pattern, leaf in rules:
        if re.search(pattern, signal, re.I):
            return leaf
    return None


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def _read(name: str) -> list[dict]:
    path = RAW / name
    if not path.exists():
        raise FileNotFoundError(
            f"missing source: {path}\nSee the source table in this file's docstring."
        )
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# BigBasket -> grocery / produce / staples / personal_care / household
# ---------------------------------------------------------------------------
#
# Rules are scoped per source Category rather than run against one flat signal.
#
# The flat version mis-mapped badly, because BigBasket's own Category strings
# contain leaf keywords: "Bakery, Cakes & Dairy" made every butter and curd a
# bakery item, and "Fruits & Vegetables" made every vegetable a fruit. Scoping
# fixes that and makes each group small enough to read and argue with.
#
# Matching runs against SubCategory first — it is curated and specific — and
# falls back to ProductName only if no subcategory rule fires. Category is
# never matched as free text.

BB_SCOPED: dict[str, list[tuple[str, str]]] = {
    "Baby Care": [
        (r"Baby Laundry", "laundry"),
        (r".", "baby_care"),
    ],
    "Bakery, Cakes & Dairy": [
        (r"Biscuit|Cookie|Rusk|Cracker|Wafer", "biscuits_cookies"),
        (r"Bread|Lavash|Khari|Cream Roll|Cake|Pastr|Brownie|Muffin|\bBun\b|Doughnut", "bakery_cakes"),
        (r"Milk|Paneer|Tofu|Cream|Butter|Margarine|Cheese|Curd|Yogurt|Shrikhand|Dairy|Ghee", "dairy_eggs"),
        (r".", "dairy_eggs"),
    ],
    "Beauty & Hygiene": [
        (r"Sanitary|Feminine|Intimate|Menstrual", "feminine_hygiene"),
        (r"Shaving|Razor|Trimmer|Beard|After Shave|Hair Remov", "shaving_grooming"),
        (r"Deodorant|Eau De|Perfume|Fragrance|Attar|Cologne|Mist", "fragrance_deodorant"),
        (r"Shampoo|Conditioner|Hair", "hair_care"),
        (r"Oral|Toothpaste|Toothbrush|Mouthwash|Dental|Floss", "oral_care"),
        (r"Bathing|Soap|Shower Gel|Body Wash|Handwash|Talc|Bath", "bath_body"),
        (r"\bLips\b|\bEyes\b|\bNails\b|\bFace\b|Makeup|Foundation|Kajal|Tools & Brushes", "makeup_cosmetics"),
        (r"Supplements & Proteins|Vitamin|Protein", "supplements_vitamins"),
        (r"First Aid|Health & Medicine|Thermometer|Sanitizer|\bMask\b", "medical_devices"),
        (r"Face Care|Body Care|Skin|Sunscreen|Moisturis|Ayurveda|Aromatherapy|Hand & Foot", "skin_care"),
        (r".", "skin_care"),
    ],
    "Beverages": [
        (r"Tea|Coffee|Decoction", "tea_coffee"),
        (r".", "beverages_soft"),
    ],
    "Cleaning & Household": [
        (r"Detergent|Laundry|Fabric|Bleach|Stain|Clothes", "laundry"),
        (r"Dishwash|Utensil|Scrubber|Sponge", "dishwashing"),
        (r"Tissue|Napkin|Foil|Cling|Garbage|Disposable|Bin\b|Dustbin", "paper_disposables"),
        (r"Toilet|Floor|Cleaner|Disinfect|Mop|Wiper|Dust Cloth|Brush|Repellent|Freshener", "cleaning_supplies"),
        (r"Bucket|Mug|Basket|Hanger|Clip|Rope|Soap Case|Dispenser|Storage|Shoe Rack", "kitchenware"),
        # party goods, rakhi and decorations have no retail root here; dropped
    ],
    "Eggs, Meat & Fish": [
        (r"Egg", "dairy_eggs"),
        (r".", "meat_fish"),
    ],
    "Foodgrains, Oil & Masala": [
        (r"Spice|Masala|Mukhwas|Haldi|Turmeric|Chilli|Hing|Salt & Sugar", "spices_masala"),
        (r"\bDals?\b|Pulses|Toor|Channa|Chana|Moong|Urad|Masoor|Rajma|Chhole|Gram", "dals_pulses"),
        (r"Flour|Atta|Sooji|Maida|Besan|Rava|Pre-Mix", "atta_flour"),
        (r"Rice|Poha|Millet|Quinoa|Grain|Ragi|Bajra|Jowar|Wheat", "rice_grains"),
        (r"Oil|Ghee|Vanaspati", "edible_oil"),
        (r"Dry Fruit|Berries|Seeds|Nuts|Almond|Cashew|Raisin|Dates", "dry_fruits_nuts"),
        (r"Salt|Sugar|Jaggery|Sweetener", "sugar_salt"),
        (r".", "spices_masala"),
    ],
    "Fruits & Vegetables": [
        (r"Leafy|Herb|Coriander|Mint", "herbs_leafy"),
        (r"Cut Fruit|Tender Coconut|Seasonal Fruit|Organic Fruit|Exotic Fruit|Fresh Fruit", "fresh_fruits"),
        (r".", "fresh_vegetables"),
    ],
    "Gourmet & World Food": [
        (r"Tea|Coffee", "tea_coffee"),
        (r"Olive Oil|Cooking Oil|Vinegar", "edible_oil"),
        (r"Dry Fruit|Berries|Roasted Seed|Nuts", "dry_fruits_nuts"),
        (r"Chocolate|Candy|Confection", "chocolates_candy"),
        (r"Pasta|Spaghetti|Noodle", "noodles_pasta"),
        (r"Cereal|Granola|Muesli|Oats|Porridge|Breakfast", "breakfast_cereal"),
        (r"Nachos|Chips|Snack|Crisps|Popcorn", "snacks_namkeen"),
        (r"Flour|Pre-Mix|Baking", "atta_flour"),
        (r"Quinoa|Grain|Rice", "rice_grains"),
        (r"Health Drink|Juice|Drink|Water", "beverages_soft"),
        (r"Sauce|Spread|Honey|Jam|Dressing|Syrup|Pickle", "sauces_spreads"),
        (r"Cheese|Butter|Milk|Cream|Yogurt", "dairy_eggs"),
        (r"Bread|Cake|Pastr|Biscuit|Cookie", "bakery_cakes"),
        (r"Meat|Fish|Prawn|Ham|Salami", "meat_fish"),
        (r"Pulses|Dal|Beans", "dals_pulses"),
        (r"Spice|Masala|Herb", "spices_masala"),
    ],
    "Kitchen, Garden & Pets": [
        (r"Pet", "pet_supplies"),
        (r"CFL|Led|Bulb|Light|Torch|Battery|Extension", "home_appliances"),
        (
            r"Container|Glassware|Bakeware|Bottle|Kitchen Tool|Strainer|Ladle|Spatula|"
            r"Kadai|Fry Pan|Plate|Bowl|Cup|Mug|Tumbler|Cookware|Casserole|Lunch|Flask|"
            r"Knife|Chopping|Cutlery|Jar|Steel|Serve",
            "kitchenware",
        ),
        # garden, tools and furnishing are out of taxonomy scope; dropped
    ],
    "Snacks & Branded Foods": [
        (r"Namkeen|Savoury|Chips|Corn Snack|Papad|Frozen Veg Snack|Nachos|Popcorn", "snacks_namkeen"),
        (r"Biscuit|Cookie|Wafer|Rusk|Cracker", "biscuits_cookies"),
        (r"Chocolate|Candy|Toffee|Confection|Mithai|Sweet", "chocolates_candy"),
        (r"Noodle|Pasta|Vermicelli|Macaroni|Soup", "noodles_pasta"),
        (r"Breakfast|Muesli|Oats|Porridge|Granola|Cereal|Flakes", "breakfast_cereal"),
        (r"Honey|Spread|Chutney|Sauce|Jam|Pickle|Ketchup|Mayonnaise", "sauces_spreads"),
        (r"Tea|Coffee", "tea_coffee"),
        (r"Juice|Drink", "beverages_soft"),
        (r"Frozen|Ready", "snacks_namkeen"),
    ],
}


def load_bigbasket() -> Iterator[CatalogItem]:
    for r in _read("bigbasket.csv"):
        rules = BB_SCOPED.get((r.get("Category") or "").strip())
        if not rules:
            continue
        sub = _clean(r.get("SubCategory")) or ""
        name = _clean(r.get("ProductName"))
        if not name:
            continue
        # subcategory is curated; only fall back to the free-text title
        leaf = _first_match(sub, rules) or _first_match(name, rules)
        if not leaf:
            continue
        price = _paise(r.get("Price"))
        if price is None:
            continue
        brand = _clean(r.get("Brand"))
        title = (
            f"{brand} {name}"
            if brand and not name.lower().startswith(brand.lower())
            else name
        )
        attrs: dict[str, str] = {}
        if pack := _clean(r.get("Quantity")):
            attrs["pack"] = pack
        if brand:
            attrs["brand"] = brand
        if disc := _paise(r.get("DiscountPrice")):
            attrs["sale_price_paise"] = str(disc)
        url = _clean(r.get("Absolute_Url")) or ""
        yield CatalogItem(
            sku=_sku("bb", url or title),
            title=title,
            brand=brand,
            category=leaf,
            attributes=attrs,
            price_paise=price,
            source="bigbasket",
            source_ref=url or None,
        )


# ---------------------------------------------------------------------------
# Karnataka excise -> alcohol
# ---------------------------------------------------------------------------

# The source's own `category` is a catch-all: 4,202 rows are labelled
# "IMFL Whisky" and include sake, cognac and sauvignon blanc. Product name wins
# over the source label; the label is only a fallback.
LIQUOR_NAME_RULES: list[tuple[str, str]] = [
    (r"sauvignon|cabernet|merlot|chardonnay|pinot|shiraz|syrah|riesling|prosecco|"
     r"champagne|\bsake\b|chianti|rioja|malbec|zinfandel|tempranillo|\brose\b|"
     r"pinotage|verdejo|grenache|\bdoc\b|\bwine\b|vino|chablis", "wine"),
    (r"cognac|brandy|armagnac|\bvsop\b|\bxo\b", "brandy"),
    (r"tequila|mezcal|liqueur|triple sec|sambuca|baileys|amaretto|mead|cider|vermouth", "liqueur"),
    (r"\brum\b|old monk|bacardi", "rum"),
    (r"vodka", "vodka"),
    (r"\bgin\b", "gin"),
    (r"beer|lager|\bale\b|stout|pilsner|brew", "beer"),
    (r"whisky|whiskey|scotch|bourbon|single malt|blended malt", "whisky"),
]

LIQUOR_CAT_MAP = {
    "IMFL Whisky": "whisky",
    "Wine": "wine",
    "Beer": "beer",
    "Brandy": "brandy",
    "IMFL Rum": "rum",
    "IMFL Vodka": "vodka",
    "IMFL Gin": "gin",
    "Tequila": "liqueur",
    "Liqueur": "liqueur",
}


def load_liquor() -> Iterator[CatalogItem]:
    for r in _read("karnataka_liquor.csv"):
        name = _clean(r.get("name"))
        if not name:
            continue
        leaf = _first_match(name, LIQUOR_NAME_RULES) or LIQUOR_CAT_MAP.get(
            (r.get("category") or "").strip()
        )
        if not leaf:
            continue
        price = _paise(r.get("mrp_per_bottle"))
        if price is None:
            continue
        size_ml = (r.get("size_ml") or "").strip()
        attrs = {"size": f"{size_ml} ml"} if size_ml else {}
        if size_ml:
            attrs["volume_ml"] = size_ml
        yield CatalogItem(
            sku=_sku("kl", f"{name}|{size_ml}"),
            title=f"{name} {size_ml} ml" if size_ml else name,
            brand=None,
            category=leaf,

            attributes=attrs,
            price_paise=price,
            source="karnataka_excise",
            source_ref=None,
        )


# ---------------------------------------------------------------------------
# Myntra -> apparel
# ---------------------------------------------------------------------------

MYNTRA_RULES: list[tuple[str, str]] = [
    (r"\bBra\b|\bBras\b|Lingerie|Nightwear|Camisole|\bRobe\b|Innerwear|\bBriefs\b|Nightdress|Loungewear|Nighty|Babydoll", "innerwear_sleepwear"),
    (r"Jacket|Sweater|Cardigan|Sweatshirt|Shawl|Coat|Blazer|Pullover|Thermal", "winterwear"),
    (r"Handbag|Backpack|Wallet|\bBelt\b|\bWatch\b|Jewellery|Earring|\bScarf\b|Clutch|\bBag\b|Sunglass", "bags_accessories"),
    (
        r"Saree|Sari|Kurta|Kurti|Salwar|Lehenga|Dupatta|Anarkali|Palazzo|Churidar|"
        r"Dress Material|Blouse|Ethnic|Sharara|Kaftan",
        "womens_ethnic",
    ),
    (r"Jeans|Trousers|Skirt|Shorts|Jumpsuit|Dress|Shrug|Tunic|\bTop\b|Playsuit|Dungaree", "womens_western"),
]


def load_myntra() -> Iterator[CatalogItem]:
    for r in _read("Fashion Dataset v2.csv"):
        products = _clean(r.get("products")) or ""
        name = _clean(r.get("name"))
        if not name:
            continue
        leaf = _first_match(f"{products} | {name}", MYNTRA_RULES)
        if not leaf:
            continue
        price = _paise(r.get("price"))
        if price is None:
            continue
        attrs: dict[str, str] = {}
        if colour := _clean(r.get("colour")):
            attrs["colour"] = colour
        brand = _clean(r.get("brand"))
        if brand:
            attrs["brand"] = brand
        if products:
            attrs["garment"] = products
        yield CatalogItem(
            sku=_sku("my", _clean(r.get("p_id")) or name),
            title=name,
            brand=brand,
            category=leaf,

            attributes=attrs,
            price_paise=price,
            source="myntra",
            source_ref=_clean(r.get("p_id")),
        )


# ---------------------------------------------------------------------------
# Flipkart -> electronics
# ---------------------------------------------------------------------------

FLIPKART_FILES = {
    "flipkart_earphones.csv": "audio_headphones",
    "flipkart_laptops.csv": "laptops_computers",
    "flipkart_mobile_data.csv": "mobiles",
}


def load_flipkart() -> Iterator[CatalogItem]:
    for fname, leaf in FLIPKART_FILES.items():
        for r in _read(fname):
            # the laptops file carries a UTF-8 BOM on its first header
            title = _clean(r.get("Title") or r.get("﻿Title"))
            if not title:
                continue
            price = _paise(r.get("Price"))
            if price is None:
                continue
            brand = title.split()[0] if title.split() else None
            attrs: dict[str, str] = {}
            if brand:
                attrs["brand"] = brand
            if orig := _paise(r.get("Original Price")):
                attrs["list_price_paise"] = str(orig)
            yield CatalogItem(
                sku=_sku("fk", title),
                title=title,
                brand=brand,
                category=leaf,
                root="",
                attributes=attrs,
                price_paise=price,
                source="flipkart",
                source_ref=None,
            )


# ---------------------------------------------------------------------------
# A-Z medicines -> pharma
# ---------------------------------------------------------------------------

OTC_PATTERN = (
    r"paracetamol|crocin|dolo|disprin|digene|gelusil|eno\b|vicks|amrutanjan|"
    r"zandu balm|iodex|moov|volini|betadine|dettol|savlon|electral|\bors\b|"
    r"cetirizine|benadryl|strepsils|halls|glycerin|antacid"
)
SUPPLEMENT_PATTERN = (
    r"vitamin|calcium|zinc|omega|multivitamin|protein|supplement|shelcal|"
    r"becosules|neurobion|folic|iron\b|b-complex|biotin"
)
DEVICE_PATTERN = r"thermometer|glucometer|oximeter|bandage|syringe|nebuli|\bmask\b|glucose strip"


def load_pharma() -> Iterator[CatalogItem]:
    for r in _read("A_Z_medicines_dataset_of_India.csv"):
        if (r.get("Is_discontinued") or "").strip().upper() == "TRUE":
            continue
        name = _clean(r.get("name"))
        if not name:
            continue
        price = _paise(r.get("price(₹)") or r.get("price(?)"))
        if price is None:
            continue
        blob = f"{name} {r.get('short_composition1','')}"
        if re.search(DEVICE_PATTERN, blob, re.I):
            leaf = "medical_devices"
        elif re.search(SUPPLEMENT_PATTERN, blob, re.I):
            leaf = "supplements_vitamins"
        elif re.search(OTC_PATTERN, blob, re.I):
            leaf = "otc_medicine"
        else:
            leaf = "prescription_medicine"
        mfr = _clean(r.get("manufacturer_name"))
        attrs: dict[str, str] = {}
        if pack := _clean(r.get("pack_size_label")):
            attrs["pack"] = pack
        if comp := _clean(r.get("short_composition1")):
            attrs["composition"] = comp
        if mfr:
            attrs["brand"] = mfr
        yield CatalogItem(
            sku=_sku("rx", _clean(r.get("id")) or name),
            title=name,
            brand=mfr,
            category=leaf,

            attributes=attrs,
            price_paise=price,
            source="az_medicines",
            source_ref=_clean(r.get("id")),
        )


# ---------------------------------------------------------------------------
# Swiggy -> restaurant
# ---------------------------------------------------------------------------

SWIGGY_RULES: list[tuple[str, str]] = [
    # a "+" almost always means a combo meal, not the first item named in it
    (r"\+|combo|thali|meal for|family pack", "main_course"),
    (r"ice cream|gulab jamun|rasgulla|brownie|halwa|kheer|dessert|sundae|falooda|"
     r"cheesecake|pastry|mousse|jalebi|rasmalai", "desserts_sweets"),
    (r"lassi|shake|cold coffee|mojito|mocktail|smoothie|iced tea|soda|juice|"
     r"cola|water bottle|buttermilk|chaas", "beverages_restaurant"),
    (r"roti|naan|paratha|kulcha|chapati|pulao|\bpulav\b|steamed rice|jeera rice|"
     r"plain rice|tandoori roti|rumali", "breads_rice"),
    (r"burger|pizza|\broll\b|momo|sandwich|fries|samosa|tikka|starter|wrap|"
     r"nugget|pakoda|pakora|spring roll|garlic bread|kebab|manchurian", "starters_snacks"),
    (r"biryani|curry|masala|gravy|thali|\bbowl\b|butter chicken|paneer|dal |"
     r"korma|handi|meal|combo|rice bowl", "main_course"),
]


def load_swiggy() -> Iterator[CatalogItem]:
    seen: set[str] = set()
    for r in _read("swiggy_sample.csv"):
        item = _clean(r.get("item"))
        if not item or len(item) < 3:
            continue
        key = item.lower()
        if key in seen:  # the same dish appears at thousands of restaurants
            continue
        price = _paise(r.get("price"))
        if price is None:
            continue
        leaf = _first_match(f"{item} | {r.get('menu','')}", SWIGGY_RULES)
        if not leaf:
            continue
        seen.add(key)
        attrs: dict[str, str] = {}
        if veg := _clean(r.get("veg_or_non_veg")):
            attrs["diet"] = veg
        if menu := _clean(r.get("menu")):
            attrs["menu_section"] = menu
        yield CatalogItem(
            sku=_sku("sw", item),
            title=item,
            brand=None,
            category=leaf,

            attributes=attrs,
            price_paise=price,
            source="swiggy",
            source_ref=None,
        )


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

LOADERS = {
    "bigbasket": load_bigbasket,
    "karnataka_excise": load_liquor,
    "myntra": load_myntra,
    "flipkart": load_flipkart,
    "az_medicines": load_pharma,
    "swiggy": load_swiggy,
}


def _sku(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"


def _rank(sku: str, seed: int) -> str:
    """Stable per-item ordering key.

    Deterministic across Python versions and platforms, unlike shuffling a list
    with `random`. Changing the seed reshuffles the whole catalog, which is what
    the reproducibility contract in 04 §7 asks a reviewer to do.
    """
    return hashlib.sha256(f"{seed}:{sku}".encode("utf-8")).hexdigest()


def collect(taxonomy: Taxonomy | None = None) -> tuple[list[CatalogItem], Counter]:
    """Load and map every source. Returns mapped items and a per-source tally."""
    tax = taxonomy or default_taxonomy()
    items: list[CatalogItem] = []
    stats: Counter = Counter()
    seen_skus: set[str] = set()

    for source, loader in LOADERS.items():
        kept = 0
        for item in loader():
            if item.category not in tax.leaves:
                raise ValueError(
                    f"{source} mapped to {item.category!r}, which is not a taxonomy leaf"
                )
            if item.sku in seen_skus:
                continue
            seen_skus.add(item.sku)
            item.root = tax.root_of(item.category)
            items.append(item)
            kept += 1
        stats[source] = kept
    return items, stats


def build(seed: int = DEFAULT_SEED, target: int = TARGET_SIZE) -> list[CatalogItem]:
    """Select a quota-balanced, deterministic catalog."""
    tax = default_taxonomy()
    items, _ = collect(tax)

    by_root: dict[str, list[CatalogItem]] = defaultdict(list)
    for it in items:
        by_root[it.root].append(it)

    scale = target / sum(QUOTAS.values())
    chosen: list[CatalogItem] = []
    for root, quota in QUOTAS.items():
        pool = sorted(by_root.get(root, []), key=lambda i: _rank(i.sku, seed))
        want = max(1, round(quota * scale))
        chosen.extend(pool[:want])

    chosen.sort(key=lambda i: (i.root, i.category, i.title))
    return chosen


def write(items: list[CatalogItem], path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(it.model_dump_json() + "\n")
    return path


def load_catalog(path: Path = OUT) -> list[CatalogItem]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not built yet — run `make dataset`")
    with path.open(encoding="utf-8") as f:
        return [CatalogItem.model_validate_json(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _report(seed: int) -> None:
    tax = default_taxonomy()
    items, per_source = collect(tax)
    print(f"mapped {len(items):,} items from {len(LOADERS)} sources\n")
    print(f"{'source':<18}{'mapped':>10}")
    for src, n in per_source.most_common():
        print(f"{src:<18}{n:>10,}")

    roots = Counter(i.root for i in items)
    print(f"\n{'root':<18}{'available':>10}{'quota':>8}")
    for root in sorted(set(roots) | set(QUOTAS)):
        print(f"{root:<18}{roots.get(root,0):>10,}{QUOTAS.get(root,0):>8}")

    built = build(seed)
    print(f"\ncatalog: {len(built)} SKUs (seed={seed})")
    print(f"{'root':<18}{'n':>5}{'leaves':>8}{'median Rs':>12}")
    by_root: dict[str, list[CatalogItem]] = defaultdict(list)
    for i in built:
        by_root[i.root].append(i)
    for root in sorted(by_root):
        g = by_root[root]
        prices = sorted(i.price_paise for i in g)
        med = prices[len(prices) // 2] / 100
        print(f"{root:<18}{len(g):>5}{len({i.category for i in g}):>8}{med:>12,.0f}")

    empty = [c for c in tax.leaf_ids if not any(i.category == c for i in built)]
    if empty:
        print(f"\nleaves with no SKU ({len(empty)}): {', '.join(empty)}")


def _sample(n: int, seed: int) -> None:
    items = build(seed)
    by_root: dict[str, list[CatalogItem]] = defaultdict(list)
    for i in items:
        by_root[i.root].append(i)
    for root in sorted(by_root):
        print(f"\n--- {root} ---")
        for i in by_root[root][: max(1, n // len(by_root))]:
            attrs = " ".join(
                f"{k}={v}" for k, v in i.attributes.items() if k not in ("brand",)
            )
            print(f"  Rs {i.price_paise/100:>9,.2f}  {i.title[:58]:<58} [{i.category}] {attrs[:40]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="write data/catalog/catalog.jsonl")
    ap.add_argument("--report", action="store_true", help="mapping coverage and composition")
    ap.add_argument("--sample", type=int, metavar="N", help="print N sample SKUs")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--size", type=int, default=TARGET_SIZE)
    args = ap.parse_args()

    if args.report:
        _report(args.seed)
    elif args.sample:
        _sample(args.sample, args.seed)
    else:
        items = build(args.seed, args.size)
        path = write(items)
        print(f"wrote {len(items)} SKUs -> {path.relative_to(ROOT)} (seed={args.seed})")


if __name__ == "__main__":
    main()
