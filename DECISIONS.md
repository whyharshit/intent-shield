# Decisions

One line per non-obvious choice, and why. Kept from day one so the reasoning
survives contact with the panel.

---

## Kill criteria — set before building anything

From 05-roadmap.md §"Kill criteria". Written down in advance so they can't be
quietly renegotiated later.

| # | Trigger | Meaning |
|---|---|---|
| K1 | The `total_within_intent + merchant_allowed` baseline catches most violations | The gap isn't real, or the dataset is too easy. Stop and reconsider. |
| K2 | Category-mapping accuracy below ~80% | The whisky demo is the headline; if it's fragile the pitch collapses. |
| K3 | The deterministic path resolves under 40% of cases | Every transaction hits an LLM. Unusable latency and cost. |
| K4 | Razorpay ships conformance checking at Global Fintech Fest | The novelty claim collapses; reposition onto the India rails mapping and the evaluation methodology. |

None have fired. K1 is not yet testable — the baseline runs in Milestone 2.

---

## Milestone 1 — dataset foundations

**D-001 · Real product data, not synthetic SKUs.**
The plan in 04 §4 called for ~800 hand-written SKUs. Every SKU in the catalog is
instead a real product from a real Indian source. A hand-written catalog would
have been styled, unconsciously, to be easy for my own category mapper to parse —
and 07 §R2 ("you generated your own data and graded yourself") is the criticism
most likely to land. Real products with messy real titles test the mapper
honestly. Sources and row counts are in the docstring of `data/generator/catalog.py`.

**D-002 · The violation labels are still synthetic, and that is unavoidable.**
No public corpus of agent-initiated purchase disputes exists. Real catalogs make
the *products* real; mandates, carts and violation injection remain generated.
This is the honest ceiling and it is stated in the README rather than glossed.

**D-003 · Alcohol comes from the Karnataka excise price list, scraped.**
No Kaggle dataset covers Indian retail liquor — Indian supermarkets don't sell
it, so BigBasket has zero alcohol rows, and the whisky case is the headline
demo. State excise price lists are official published data with better
provenance than any scrape of a retailer. 8,180 SKUs with official MRPs.
`robots.txt` on the source permits `/liquor-price-list/`.

**D-004 · Footwear is out; V4 ATTRIBUTE_MISMATCH runs on colour instead of size.**
The AP2 spec's own example ("size 10, white or grey running shoes") is a
footwear case, but no footwear source was obtained. Apparel carries a real
`colour` attribute on >90% of rows, so attribute mismatch is still testable —
"blue" against "red or maroon" rather than "size 9" against "size 10". Weaker
because colour is a closed vocabulary and size carries unit ambiguity (UK 10 vs
US 10), which was one of the more interesting adversarial cases. Reinstate if a
footwear source appears.

**D-005 · Size lives on the cart line, not the catalog.**
No scraped catalog carries product-level size, because size is a variant
dropdown on the product page rather than an attribute of the product. This is
structural, not a gap in what was downloaded. Carts are generated regardless, so
size belongs on the line item — which is also where a real checkout puts it.

**D-006 · Source categories are mapped to the taxonomy by ordered regex, not embeddings.**
The catalog's own labels are the ground truth the eval grades against. Deriving
them with the same probabilistic mapper the system is being graded on would make
the evaluation circular. This is a build-time join: deterministic, inspectable,
arguable. Consistent with the governing rule — an embedding here would be a
model doing a job a join can do.

**D-007 · Mapping rules are scoped per source category.**
The first version matched one flat signal that included BigBasket's own
`Category` string, and those strings contain leaf keywords: "Bakery, **Cakes** &
Dairy" made every butter and curd a bakery item, "**Fruits** & Vegetables" made
every vegetable a fruit. Rules now run per source category, against SubCategory
first and the product title only as a fallback. Two regex bugs came out of the
same review: `Bra\b` matched "Chha**bra**" and `Bread` matched "**Bread**ed".

**D-008 · Unmappable rows are dropped, never guessed.**
`--report` prints what each source contributed. Festive goods, garden tools and
home furnishing have no home in a 12-root retail taxonomy and are excluded
rather than forced into the nearest leaf. Only 800 of ~295,000 mapped rows are
needed, so precision costs nothing.

**D-009 · Catalog composition is quota-balanced, not proportional to the sources.**
BigBasket is 46% cosmetics and 1.4% fresh produce — upside-down for the weekly-
groceries mandate the demo lives in. `QUOTAS` in `catalog.py` rebalances toward
that world while keeping enough alcohol, apparel, electronics and pharma for
violations to be injected from.

**D-010a · Sampling is stratified by price and balanced across leaves.**
Taking the first N in hash order sampled price randomly. On a quota of 15 it
drew whiskies at Rs 28 and Rs 32,550 and nothing in between — the headline
demo needs a cart landing just under Rs 2,000, and the catalog could not
express it. Selection now shares each root's quota evenly across the leaves
that have stock, then systematically samples each leaf across its real price
range. Alcohol went from 59 wines and 1 beer to an even spread over all eight
leaves; leaf coverage rose from 57 to 62.

**D-010 · Selection is by stable hash, not `random.shuffle`.**
`sha256(seed:sku)` sorts identically across Python versions and platforms. The
reproducibility contract asks a reviewer to change the seed and re-run; that
only means something if the same seed reproduces on their machine.

**D-011 · `data/raw/` is gitignored; the derived catalog ships instead.**
The sources are third-party scrapes redistributed on Kaggle under licences their
uploaders could not actually grant. The repo carries the loader, the mapping
rules and a source table — not the scraped files. Karnataka excise data is
government-published and could be committed; it is excluded for consistency.

**D-012 · A 13th taxonomy root, `services`, for fees and add-ons.**
04 §2 marks V11 ADD_ON_CREEP as needing an LLM. Express shipping, extended
warranty and insurance are line items with a type, so membership in a `services`
leaf answers it by comparison. Follows the governing rule; noted as a deviation
from the taxonomy shape in 03 §3.2.

**D-013 · Money is integer paise. Datetimes are timezone-aware. `extra="forbid"`.**
Three invariants in `warrant/models.py`. Float rupees introduce rounding drift
in a ceiling comparison. A naive `expires_at` raises when compared against an
aware `now`, inside the payment path. An unrecognised field means the sender and
this service disagree about what is being authorised — fail closed at the
boundary. Tested in `tests/test_models.py`.

**D-014 · Cart arithmetic is enforced by the schema, not the checker.**
If a cart claims a total its line items don't sum to, the right answer is to
reject the document, not to pick which number to trust. This also makes the
"shipping pushes it over the cap" adversarial case a schema guarantee rather
than something C3 has to remember.

**D-015 · An empty cart parses successfully.**
04 §3 lists it as an adversarial case that must not crash. Rejecting it at the
schema boundary would turn a case the pipeline should *escalate* on into a parse
error that tells the caller nothing.

**D-016 · A `REFUSE` decision must carry a failing check.**
Enforced in the `Decision` model. Without it, a bug that drops the failing check
still emits a plausible refusal, and the audit record — the entire point of the
log as dispute evidence — no longer explains the verdict it carries.

**D-017 · Core models live in `warrant/models.py`.**
03 §6's layout has no shared model module; `IntentMandate`, `Cart` and
`Decision` are used by every package, so they sit at the package root rather
than being duplicated or imported sideways from `extract/schema.py`.

---

## Open problems in the design docs

Raised before building. Recorded here so they're resolved deliberately.

**P-001 · C3's denied-category check depends on C4 stage 1.**
The architecture in 03 §1 runs the deterministic checker before category
mapping, but "no line item maps to a denied category" needs the mapping to exist.
Either the mapper runs before the rules, or the denied-category check moves into
C4. Resolve when C3 is built.

**P-002 · No schema for mandate state.**
Frequency (V9) and cumulative spend need a ledger of prior approvals per
mandate. No model in 03 §2 carries it, and the generator will need to emit that
history per pair. Not built in Milestone 1 — the seven models the brief listed
are implemented as specified.

**P-003 · `merchants_allowed: []` is undefined.**
Empty could mean allow-all or deny-all. It decides what the baseline catches,
which is the K1 go/no-go number. Must be pinned before the baseline runs.

**P-004 · Escalation is counted as a catch for Warrant; the baseline can't escalate.**
04 §5 defines violation recall as "correctly refused **or escalated**", but the
baseline is two-way. Report refuse-only recall alongside, or the comparison is
asymmetric in Warrant's favour and a reviewer will say so.

**P-005 · Per-violation-type breakdown is underpowered at n=400.**
400 test pairs across 12 violation types is ~15 each; per-type recall carries a
95% CI of roughly ±25 points, and 04 §6 makes that table a headline artifact.
The generator controls the distribution, so oversample rare types in test or
raise the test split.

**P-006 · Calibration only has the LLM subset to fit on.**
Isotonic regression fits raw model confidence, but rules resolve most cases with
no confidence to calibrate. If ~15% of ~400 validation pairs reach the model,
that's ~60 points for isotonic regression, a reliability diagram and an ECE.
Thin. May need a larger validation split.

---

## Measured limitations

Things that are true of the build as it stands, found by looking rather than
assumed.

**L-001 · Category mapping is imperfect and the residue is visible.**
After D-007, spot-checking still finds errors: an anti-skid floor mat maps to
`cleaning_supplies`, a moong dal laddoo (a sweet) maps to `dals_pulses`. These
are ground-truth labels, so the error rate is a floor on measured accuracy.
Quantify it against a hand-labelled sample before reporting category accuracy.

**L-002 · The OTC / prescription split in pharma is weak.**
The A-Z dataset has no prescription flag, so the split is keyword-driven and
wrong at the margin — an IV infusion currently lands in `otc_medicine`. Both
leaves sit under a restricted root, so the root-level check is unaffected.

**L-003 · The source's own liquor categories are unreliable, and this bit.**
4,202 rows are labelled "IMFL Whisky" and include sake, cognac and sauvignon
blanc. The first build inherited that label and filled the whisky leaf with
Italian wine — Ricossa Gavi, Te Mata Gamay Noir. `whisky` is now assigned only
on positive evidence in the product name; "IMFL Whisky" was removed from the
fallback map entirely and unmatched rows are dropped. Root-level `alcohol` was
never affected, so the denied-category check was always correct — but the demo
narrative would have shown a wine labelled whisky on stage.

The test that should have caught it asserted whisky *existed*, not that it was
whisky, so it passed throughout. Replaced with a contents assertion.

**L-004 · Six taxonomy leaves have no SKUs.**
Tobacco (no source obtained), footwear (D-004), men's apparel and bags (the
Myntra source is women's only), and the `services` leaves (add-ons are generated
at cart-build time, not catalog entries). The taxonomy keeps them: a mandate can
deny a category that has no stock behind it, and it should still parse.
