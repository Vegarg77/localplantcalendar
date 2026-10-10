"""Bundled plant library.

Every crop starts from a *profile* (shared defaults for a group of similar
plants) and overrides whatever differs.  Values are compiled from public
sources: university extension planting guides (days to maturity, spacing,
soil temperatures), FAO Irrigation & Drainage Paper 56 (crop coefficients,
rooting depth, allowable depletion) and extension nutrient-management guides
(seasonal nitrogen demand, legume nitrogen credits).

Units
-----
temperatures °F, spacing/depth in inches, nitrogen in lb N per acre
(converted to per-bed amounts in the UI), days for durations.

Field reference
---------------
frost          tender | semi | hardy | very_hardy  (damage at 32/28/24/15 °F)
method         direct | transplant | either   (``prefer`` picks the default)
indoor_weeks   [min, max] weeks from indoor sowing to transplant
dtm            [min, max] days to (first) harvest, counted from ``dtm_from``
germ_min/max   soil-temperature range for germination
grow_min       minimum mean daily temperature for useful growth
heat_max       mean daily high above which quality fails at maturity (bolting,
               bitterness, poor heading).  ``None`` = heat tolerant
heat_stress    daily high that triggers a heat alert (blossom drop etc.); a
               sustained average above it blocks warm-season planting dates
night_max      mean night low above which fruit set fails (tomatoes)
base_f         base temperature for growing-degree-day accounting
kc             FAO-56 crop coefficients [initial, mid-season, late]
root_in        effective rooting depth used for watering
p              fraction of available water that can be depleted before stress
feeder         heavy | medium | light | fixer
n_demand       seasonal nitrogen drawn from the soil (lb N/acre)
n_fix          nitrogen left in residue/roots by legumes (lb N/acre)
residue_frac   fraction of crop N left in residues
residue_cn     low | medium | high  carbon:nitrogen ratio of residues
special        anchor-based timing for overwintering crops & perennials:
               {"plant": (anchor, offset, anchor, offset),
                "harvest": (anchor, offset, anchor, offset),
                "kind": "overwinter" | "perennial" | "winterkill",
                "first_harvest_year": n}
               anchors: "lsf" (median last spring frost), "fff" (median first
               fall frost), "lsf+1" (next year's last spring frost)
zone           (min, max) USDA hardiness zones for perennials (6.5 = zone 6b);
               below min winters kill it, above max there is too little chill
soil_pref      "loose" for root/tuber crops that deform or rot in heavy clay
container_ok   perennial that can live in a pot and overwinter indoors
"""

from __future__ import annotations

import copy

PROFILES: dict[str, dict] = {
    "warm_fruit": dict(
        category="vegetable", lifecycle="annual", season="warm", frost="tender",
        method="transplant", prefer="transplant", indoor_weeks=[6, 8], dtm_from="transplant",
        dtm=[70, 85], harvest_days=60, germ_min=60, germ_max=95, germ_days=[6, 12],
        grow_min=58, heat_max=None, heat_stress=92, night_max=None, base_f=50,
        succession=None, spacing=24, row=36, depth=0.25, sun="full",
        kc=[0.6, 1.15, 0.8], root_in=24, p=0.4,
        feeder="heavy", n_demand=110, n_fix=0, residue_frac=0.4, residue_cn="medium",
        ph=[6.0, 6.8], diseases=["late_blight", "fungal_leaf"],
    ),
    "cucurbit": dict(
        category="vegetable", lifecycle="annual", season="warm", frost="tender",
        method="either", prefer="direct", indoor_weeks=[3, 4], dtm_from="sow",
        dtm=[50, 65], harvest_days=45, germ_min=60, germ_max=95, germ_days=[4, 10],
        grow_min=60, heat_max=None, heat_stress=95, base_f=50, succession=None,
        spacing=24, row=48, depth=1.0, sun="full",
        kc=[0.5, 1.0, 0.75], root_in=24, p=0.5,
        feeder="heavy", n_demand=90, n_fix=0, residue_frac=0.4, residue_cn="low",
        ph=[6.0, 7.0], diseases=["powdery_mildew", "downy_mildew"],
    ),
    "warm_legume": dict(
        category="vegetable", lifecycle="annual", season="warm", frost="tender",
        method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
        dtm=[50, 60], harvest_days=21, germ_min=60, germ_max=90, germ_days=[6, 12],
        grow_min=58, heat_max=None, heat_stress=90, base_f=50, succession=21,
        spacing=4, row=18, depth=1.0, sun="full",
        kc=[0.5, 1.05, 0.9], root_in=18, p=0.45,
        feeder="fixer", n_demand=30, n_fix=40, residue_frac=0.0, residue_cn="low",
        ph=[6.0, 7.0], diseases=["fungal_leaf"],
    ),
    "cool_legume": dict(
        category="vegetable", lifecycle="annual", season="cool", frost="hardy",
        method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
        dtm=[60, 70], harvest_days=21, germ_min=40, germ_max=75, germ_days=[7, 14],
        grow_min=40, heat_max=85, heat_stress=85, base_f=40, succession=None,
        spacing=2, row=18, depth=1.0, sun="full",
        kc=[0.5, 1.15, 1.1], root_in=18, p=0.35,
        feeder="fixer", n_demand=20, n_fix=40, residue_frac=0.0, residue_cn="low",
        ph=[6.0, 7.5], diseases=["powdery_mildew"],
    ),
    "brassica_tp": dict(
        category="vegetable", lifecycle="annual", season="cool", frost="hardy",
        method="either", prefer="transplant", indoor_weeks=[4, 6], dtm_from="transplant",
        dtm=[55, 80], harvest_days=21, germ_min=45, germ_max=85, germ_days=[4, 10],
        grow_min=40, heat_max=85, heat_stress=88, base_f=40, succession=None,
        spacing=18, row=24, depth=0.5, sun="full",
        kc=[0.7, 1.05, 0.95], root_in=18, p=0.45,
        feeder="heavy", n_demand=150, n_fix=0, residue_frac=0.4, residue_cn="low",
        ph=[6.0, 7.5], diseases=["downy_mildew"],
    ),
    "brassica_fast": dict(
        category="vegetable", lifecycle="annual", season="cool", frost="hardy",
        method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
        dtm=[35, 50], harvest_days=14, germ_min=45, germ_max=85, germ_days=[3, 10],
        grow_min=40, heat_max=80, heat_stress=85, base_f=35, succession=14,
        spacing=4, row=12, depth=0.5, sun="full",
        kc=[0.7, 0.95, 0.9], root_in=12, p=0.4,
        feeder="medium", n_demand=60, n_fix=0, residue_frac=0.2, residue_cn="low",
        ph=[6.0, 7.5], diseases=["downy_mildew"],
    ),
    "leafy": dict(
        category="vegetable", lifecycle="annual", season="cool", frost="semi",
        method="either", prefer="direct", indoor_weeks=[3, 5], dtm_from="sow",
        dtm=[40, 55], harvest_days=21, germ_min=40, germ_max=80, germ_days=[4, 10],
        grow_min=40, heat_max=80, heat_stress=85, base_f=35, succession=14,
        spacing=6, row=12, depth=0.25, sun="full",
        kc=[0.7, 1.0, 0.95], root_in=12, p=0.3,
        feeder="medium", n_demand=90, n_fix=0, residue_frac=0.15, residue_cn="low",
        ph=[6.0, 7.0], diseases=["downy_mildew"],
    ),
    "root": dict(
        category="vegetable", lifecycle="annual", season="cool", frost="hardy",
        method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
        dtm=[60, 75], harvest_days=30, germ_min=45, germ_max=85, germ_days=[7, 21],
        grow_min=40, heat_max=88, heat_stress=92, base_f=40, succession=21,
        spacing=3, row=12, depth=0.25, sun="full",
        kc=[0.7, 1.05, 0.95], root_in=18, p=0.35,
        feeder="light", n_demand=70, n_fix=0, residue_frac=0.3, residue_cn="low",
        ph=[6.0, 7.0], diseases=[],
    ),
    "allium": dict(
        category="vegetable", lifecycle="annual", season="cool", frost="hardy",
        method="transplant", prefer="transplant", indoor_weeks=[8, 10], dtm_from="transplant",
        dtm=[90, 120], harvest_days=21, germ_min=50, germ_max=85, germ_days=[7, 14],
        grow_min=40, heat_max=None, heat_stress=95, base_f=40, succession=None,
        spacing=4, row=12, depth=0.25, sun="full",
        kc=[0.7, 1.05, 0.75], root_in=12, p=0.3,
        feeder="medium", n_demand=100, n_fix=0, residue_frac=0.1, residue_cn="low",
        ph=[6.0, 7.0], diseases=["downy_mildew"],
    ),
    "warm_direct": dict(
        category="vegetable", lifecycle="annual", season="warm", frost="tender",
        method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
        dtm=[60, 80], harvest_days=30, germ_min=60, germ_max=95, germ_days=[5, 10],
        grow_min=60, heat_max=None, heat_stress=98, base_f=50, succession=None,
        spacing=12, row=30, depth=1.0, sun="full",
        kc=[0.5, 1.0, 0.8], root_in=24, p=0.5,
        feeder="medium", n_demand=80, n_fix=0, residue_frac=0.3, residue_cn="medium",
        ph=[6.0, 7.0], diseases=[],
    ),
    "herb_warm": dict(
        category="herb", lifecycle="annual", season="warm", frost="tender",
        method="either", prefer="transplant", indoor_weeks=[4, 6], dtm_from="sow",
        dtm=[50, 70], harvest_days=90, germ_min=60, germ_max=90, germ_days=[5, 10],
        grow_min=58, heat_max=None, heat_stress=95, base_f=50, succession=None,
        spacing=10, row=18, depth=0.25, sun="full",
        kc=[0.6, 1.0, 0.9], root_in=12, p=0.4,
        feeder="light", n_demand=50, n_fix=0, residue_frac=0.1, residue_cn="low",
        ph=[6.0, 7.5], diseases=[],
    ),
    "herb_cool": dict(
        category="herb", lifecycle="annual", season="cool", frost="semi",
        method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
        dtm=[45, 65], harvest_days=40, germ_min=50, germ_max=85, germ_days=[7, 14],
        grow_min=40, heat_max=85, heat_stress=90, base_f=40, succession=21,
        spacing=6, row=12, depth=0.25, sun="full",
        kc=[0.6, 1.0, 0.9], root_in=12, p=0.4,
        feeder="light", n_demand=50, n_fix=0, residue_frac=0.1, residue_cn="low",
        ph=[6.0, 7.5], diseases=[],
    ),
    "herb_perennial": dict(
        category="herb", lifecycle="perennial", season="cool", frost="hardy",
        method="transplant", prefer="transplant", indoor_weeks=[8, 10], dtm_from="transplant",
        dtm=[60, 90], harvest_days=120, germ_min=60, germ_max=85, germ_days=[7, 21],
        grow_min=45, heat_max=None, heat_stress=98, base_f=45, succession=None,
        spacing=12, row=18, depth=0.125, sun="full",
        kc=[0.4, 0.8, 0.7], root_in=18, p=0.5,
        feeder="light", n_demand=40, n_fix=0, residue_frac=0.0, residue_cn="medium",
        ph=[6.0, 7.5], diseases=[],
        special={"plant": ("lsf", -7, "lsf", 28), "harvest": ("lsf", 45, "fff", 0),
                 "kind": "perennial", "first_harvest_year": 1},
    ),
    "perennial_veg": dict(
        category="vegetable", lifecycle="perennial", season="cool", frost="very_hardy",
        method="transplant", prefer="transplant", indoor_weeks=None, dtm_from="transplant",
        dtm=[60, 90], harvest_days=45, germ_min=50, germ_max=85, germ_days=[14, 21],
        grow_min=45, heat_max=None, heat_stress=95, base_f=40, succession=None,
        spacing=18, row=48, depth=6.0, sun="full",
        kc=[0.5, 0.95, 0.9], root_in=36, p=0.45,
        feeder="medium", n_demand=80, n_fix=0, residue_frac=0.0, residue_cn="medium",
        ph=[6.0, 7.5], diseases=[],
    ),
    "fruit": dict(
        category="fruit", lifecycle="perennial", season="cool", frost="very_hardy",
        method="transplant", prefer="transplant", indoor_weeks=None, dtm_from="transplant",
        dtm=[365, 730], harvest_days=30, germ_min=50, germ_max=85, germ_days=[14, 28],
        grow_min=45, heat_max=None, heat_stress=98, base_f=45, succession=None,
        spacing=36, row=72, depth=0.0, sun="full",
        kc=[0.5, 0.95, 0.75], root_in=36, p=0.5,
        feeder="medium", n_demand=60, n_fix=0, residue_frac=0.0, residue_cn="high",
        ph=[6.0, 6.8], diseases=["fungal_leaf"],
    ),
    "flower_warm": dict(
        category="flower", lifecycle="annual", season="warm", frost="tender",
        method="either", prefer="direct", indoor_weeks=[4, 6], dtm_from="sow",
        dtm=[60, 75], harvest_days=75, germ_min=65, germ_max=90, germ_days=[5, 10],
        grow_min=58, heat_max=None, heat_stress=100, base_f=50, succession=None,
        spacing=12, row=18, depth=0.25, sun="full",
        kc=[0.5, 0.9, 0.8], root_in=12, p=0.5,
        feeder="light", n_demand=40, n_fix=0, residue_frac=0.3, residue_cn="medium",
        ph=[6.0, 7.5], diseases=["powdery_mildew"],
    ),
    "flower_cool": dict(
        category="flower", lifecycle="annual", season="cool", frost="semi",
        method="direct", prefer="direct", indoor_weeks=[6, 8], dtm_from="sow",
        dtm=[50, 70], harvest_days=60, germ_min=50, germ_max=75, germ_days=[7, 14],
        grow_min=45, heat_max=85, heat_stress=90, base_f=40, succession=None,
        spacing=9, row=12, depth=0.25, sun="full",
        kc=[0.5, 0.9, 0.8], root_in=12, p=0.5,
        feeder="light", n_demand=40, n_fix=0, residue_frac=0.3, residue_cn="medium",
        ph=[6.0, 7.5], diseases=[],
    ),
    "cover_winter": dict(
        category="cover", lifecycle="annual", season="cool", frost="very_hardy",
        method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
        dtm=[150, 220], harvest_days=7, germ_min=40, germ_max=85, germ_days=[5, 10],
        grow_min=35, heat_max=None, heat_stress=95, base_f=35, succession=None,
        spacing=1, row=6, depth=1.0, sun="full",
        kc=[0.4, 1.0, 0.9], root_in=24, p=0.55,
        feeder="medium", n_demand=50, n_fix=0, residue_frac=1.0, residue_cn="high",
        ph=[5.5, 7.5], diseases=[],
    ),
    "cover_summer": dict(
        category="cover", lifecycle="annual", season="warm", frost="tender",
        method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
        dtm=[40, 60], harvest_days=7, germ_min=60, germ_max=95, germ_days=[3, 7],
        grow_min=58, heat_max=None, heat_stress=105, base_f=50, succession=None,
        spacing=1, row=6, depth=0.75, sun="full",
        kc=[0.4, 1.0, 0.9], root_in=24, p=0.55,
        feeder="light", n_demand=30, n_fix=0, residue_frac=1.0, residue_cn="low",
        ph=[5.5, 7.5], diseases=[],
    ),
}

# Minimum years before the same family should return to the same bed.
FAMILY_RETURN_YEARS = {
    "Solanaceae": 3, "Brassicaceae": 3, "Amaryllidaceae": 3,
    "Cucurbitaceae": 2, "Apiaceae": 2, "Amaranthaceae": 2, "Fabaceae": 2,
}

FAMILY_COMMON = {
    "Solanaceae": "Nightshades", "Cucurbitaceae": "Squash family", "Fabaceae": "Legumes",
    "Brassicaceae": "Brassicas", "Amaranthaceae": "Beet & spinach family",
    "Asteraceae": "Daisy family (lettuce)", "Apiaceae": "Carrot family",
    "Amaryllidaceae": "Alliums", "Poaceae": "Grasses (corn, grains)",
    "Lamiaceae": "Mint family", "Malvaceae": "Mallows (okra)",
    "Convolvulaceae": "Morning glory (sweet potato)", "Polygonaceae": "Buckwheat family",
    "Rosaceae": "Rose family", "Ericaceae": "Heath family", "Vitaceae": "Grapes",
    "Moraceae": "Fig family", "Tropaeolaceae": "Nasturtiums", "Boraginaceae": "Borage family",
    "Aizoaceae": "Ice plant family", "Basellaceae": "Basella", "Montiaceae": "Miner's lettuce",
    "Caprifoliaceae": "Honeysuckle family (mâche)", "Asparagaceae": "Asparagus family",
    "Plantaginaceae": "Plantain family", "Zingiberaceae": "Ginger family",
    "Lauraceae": "Laurel family (avocado)", "Rutaceae": "Citrus family",
    "Oleaceae": "Olive family", "Lythraceae": "Pomegranate family",
    "Musaceae": "Banana family", "Anacardiaceae": "Cashew family (mango)",
}

FROST_THRESHOLD_F = {"tender": 32, "semi": 28, "hardy": 24, "very_hardy": 15}

_PLANTS: list[dict] = []


def P(pid: str, name: str, latin: str, family: str, profile: str, **kw) -> None:
    base = copy.deepcopy(PROFILES[profile])
    base.update(kw)
    base.update(id=pid, name=name, latin=latin, family=family, profile=profile)
    base.setdefault("companions", [])
    base.setdefault("avoid", [])
    base.setdefault("tips", "")
    base.setdefault("special", None)
    _PLANTS.append(base)


# ---------------------------------------------------------------- nightshades
P("tomato", "Tomato (slicing)", "Solanum lycopersicum", "Solanaceae", "warm_fruit",
  dtm=[70, 85], n_demand=120, night_max=76,
  companions=["basil", "marigold", "carrot", "onion_bulb", "parsley", "borage", "nasturtium"],
  avoid=["fennel_bulb", "potato", "sweet_corn", "cabbage", "kohlrabi"],
  tips="Plant deep — roots form along the buried stem. Stake or cage at planting. Even "
       "moisture under mulch prevents blossom-end rot and cracking. Nights below 55°F or "
       "days above 90°F stop fruit set.")
P("cherry_tomato", "Tomato (cherry)", "Solanum lycopersicum var. cerasiforme", "Solanaceae",
  "warm_fruit", dtm=[55, 70], harvest_days=80, n_demand=110, night_max=78,
  companions=["basil", "marigold", "carrot", "onion_bulb", "parsley", "borage"],
  avoid=["fennel_bulb", "potato", "sweet_corn"],
  tips="The most forgiving tomato for short or cool seasons. Indeterminate types need "
       "a 6-ft stake or cage.")
P("paste_tomato", "Tomato (paste/Roma)", "Solanum lycopersicum", "Solanaceae", "warm_fruit",
  dtm=[75, 85], harvest_days=40, spacing=18, night_max=76,
  companions=["basil", "marigold", "carrot", "parsley"], avoid=["fennel_bulb", "potato"],
  tips="Mostly determinate: fruit ripens in a 3–5 week flush — ideal for canning.")
P("pepper_sweet", "Pepper (sweet/bell)", "Capsicum annuum", "Solanaceae", "warm_fruit",
  dtm=[65, 80], indoor_weeks=[8, 10], germ_min=65, grow_min=60, heat_stress=90,
  spacing=18, row=24, kc=[0.6, 1.05, 0.9], p=0.3, n_demand=120,
  companions=["basil", "onion_bulb", "carrot", "marigold"], avoid=["fennel_bulb", "kohlrabi"],
  tips="Peppers sulk in cold soil: wait for nights above 55°F. Blossoms drop above 90°F "
       "days or below 60°F nights. Let fruit ripen fully for color and sweetness.")
P("pepper_hot", "Pepper (hot/chile)", "Capsicum annuum / C. chinense", "Solanaceae",
  "warm_fruit", dtm=[70, 95], indoor_weeks=[8, 10], germ_min=70, grow_min=60,
  heat_stress=95, spacing=18, row=24, kc=[0.6, 1.05, 0.9], p=0.3, n_demand=100,
  companions=["basil", "onion_bulb", "carrot", "marigold"], avoid=["fennel_bulb"],
  tips="Habaneros and other C. chinense need the long end of the range and warm soil "
       "(80°F) to germinate — use a heat mat.")
P("eggplant", "Eggplant", "Solanum melongena", "Solanaceae", "warm_fruit",
  dtm=[65, 80], indoor_weeks=[8, 10], germ_min=70, grow_min=62, heat_stress=95,
  kc=[0.6, 1.05, 0.9], spacing=24, n_demand=120,
  companions=["bush_bean", "marigold", "thyme"], avoid=["fennel_bulb"],
  tips="Loves heat. Row cover early in the season stops flea beetles; remove it at bloom.")
P("tomatillo", "Tomatillo", "Physalis philadelphica", "Solanaceae", "warm_fruit",
  dtm=[65, 85], spacing=36, n_demand=90, diseases=["fungal_leaf"],
  companions=["basil", "marigold"], tips="Not self-fertile — plant at least two.")
P("ground_cherry", "Ground cherry", "Physalis pruinosa", "Solanaceae", "warm_fruit",
  dtm=[65, 75], spacing=24, n_demand=70, diseases=[],
  tips="Fruit drops when ripe; harvest from the ground in its papery husk.")
P("potato", "Potato", "Solanum tuberosum", "Solanaceae", "root",
  season="cool", frost="semi", germ_min=45, germ_max=80, germ_days=[14, 21],
  dtm=[70, 120], harvest_days=30, grow_min=45, heat_max=88, heat_stress=90,
  spacing=12, row=30, depth=4.0, kc=[0.5, 1.15, 0.75], root_in=18, p=0.35,
  feeder="heavy", n_demand=130, residue_frac=0.2, ph=[5.0, 6.5],
  diseases=["late_blight", "fungal_leaf"], succession=None,
  companions=["bush_bean", "marigold", "cabbage", "sweet_corn"],
  avoid=["tomato", "cucumber", "winter_squash", "sunflower"],
  tips="Plant seed potatoes 2–4 weeks before last frost. Hill soil over stems as they "
       "grow. New potatoes ~60 days; storage potatoes after vines die back. Tuber set "
       "stalls when soil passes ~85°F.")

# ------------------------------------------------------------------ cucurbits
P("cucumber", "Cucumber", "Cucumis sativus", "Cucurbitaceae", "cucurbit",
  dtm=[50, 65], harvest_days=40, spacing=12, row=36, n_demand=90, succession=30,
  companions=["bush_bean", "pole_bean", "radish", "dill", "nasturtium", "sunflower"],
  avoid=["potato", "sage"],
  tips="Trellis to save space and keep fruit clean. Pick every 1–2 days — over-mature "
       "fruit shuts down production. Bitterness comes from drought or heat stress.")
P("summer_squash", "Summer squash / Zucchini", "Cucurbita pepo", "Cucurbitaceae", "cucurbit",
  dtm=[45, 60], harvest_days=60, spacing=24, row=36, kc=[0.5, 0.95, 0.75], n_demand=90,
  succession=40,
  companions=["nasturtium", "bush_bean", "borage", "marigold"], avoid=["potato"],
  tips="A second sowing ~6 weeks after the first outlasts squash vine borer and "
       "powdery mildew. Harvest at 6–8 inches.")
P("winter_squash", "Winter squash (butternut, acorn…)", "Cucurbita spp.", "Cucurbitaceae",
  "cucurbit", dtm=[80, 110], harvest_days=30, spacing=36, row=72, n_demand=90,
  companions=["sweet_corn", "pole_bean", "nasturtium", "borage"], avoid=["potato"],
  tips="Harvest when the rind resists a thumbnail and the stem corks — before hard "
       "frost. Cure 10 days at 80°F for storage.")
P("pumpkin", "Pumpkin", "Cucurbita pepo / C. maxima", "Cucurbitaceae", "cucurbit",
  dtm=[90, 120], harvest_days=30, spacing=48, row=96, n_demand=90,
  companions=["sweet_corn", "pole_bean", "nasturtium"], avoid=["potato"],
  tips="Count back from when you want them (e.g. Halloween) and add 2 weeks.")
P("cantaloupe", "Melon (cantaloupe/muskmelon)", "Cucumis melo", "Cucurbitaceae", "cucurbit",
  dtm=[70, 90], harvest_days=30, germ_min=65, grow_min=65, spacing=24, row=60,
  kc=[0.5, 0.85, 0.6], n_demand=90,
  companions=["nasturtium", "marigold", "radish"], avoid=["potato"],
  tips="Ripe when it slips from the vine with light pressure. Cut back water as fruit "
       "ripens for better sugar.")
P("honeydew", "Melon (honeydew/casaba)", "Cucumis melo Inodorus group", "Cucurbitaceae",
  "cucurbit", dtm=[80, 100], harvest_days=30, germ_min=65, grow_min=65, spacing=24,
  row=60, kc=[0.5, 0.85, 0.6], n_demand=90,
  tips="Needs a long, hot season; does not slip — ripe when the blossom end softens.")
P("watermelon", "Watermelon", "Citrullus lanatus", "Cucurbitaceae", "cucurbit",
  dtm=[75, 95], harvest_days=30, germ_min=70, grow_min=65, spacing=36, row=72,
  kc=[0.4, 1.0, 0.75], n_demand=90, heat_stress=100,
  companions=["nasturtium", "radish"], avoid=["potato"],
  tips="Ripe when the tendril nearest the fruit dries and the ground spot turns creamy.")
P("luffa", "Luffa gourd", "Luffa aegyptiaca", "Cucurbitaceae", "cucurbit",
  dtm=[90, 120], harvest_days=30, germ_min=70, grow_min=65, spacing=24, row=60,
  tips="Needs a long, hot season and a strong trellis. Young fruit is edible; mature "
       "fruit becomes sponges.")

# -------------------------------------------------------------------- legumes
P("bush_bean", "Bean (bush snap)", "Phaseolus vulgaris", "Fabaceae", "warm_legume",
  dtm=[50, 60], harvest_days=21, succession=21,
  companions=["carrot", "cucumber", "potato", "summer_squash", "eggplant", "marigold"],
  avoid=["onion_bulb", "garlic", "leek", "chives", "fennel_bulb"],
  tips="Sow every 3 weeks for a steady harvest. Avoid working wet plants (spreads "
       "disease). Blossoms drop above ~90°F.")
P("pole_bean", "Bean (pole)", "Phaseolus vulgaris", "Fabaceae", "warm_legume",
  dtm=[60, 70], harvest_days=50, spacing=6, row=30, succession=None, n_fix=50,
  companions=["sweet_corn", "winter_squash", "cucumber", "radish"],
  avoid=["onion_bulb", "garlic", "beet", "sunflower"],
  tips="Set the trellis before sowing. Keep picking to keep vines producing.")
P("lima_bean", "Bean (lima/butter)", "Phaseolus lunatus", "Fabaceae", "warm_legume",
  dtm=[65, 90], harvest_days=30, germ_min=65, grow_min=60, spacing=6, row=24,
  succession=None,
  tips="Needs warmer soil than snap beans — cold, wet soil rots seed.")
P("cowpea", "Southern pea / Cowpea", "Vigna unguiculata", "Fabaceae", "warm_legume",
  dtm=[60, 90], harvest_days=30, germ_min=65, grow_min=62, heat_stress=102,
  kc=[0.4, 1.0, 0.6], spacing=4, row=24, n_fix=60, succession=None,
  tips="Thrives in heat and poor soil where snap beans fail.")
P("yardlong_bean", "Yardlong bean", "Vigna unguiculata subsp. sesquipedalis", "Fabaceae",
  "warm_legume", dtm=[60, 80], harvest_days=60, germ_min=65, grow_min=65,
  heat_stress=102, spacing=6, row=30, succession=None,
  tips="Grow on a tall trellis; pick pods at pencil thickness.")
P("edamame", "Edamame (soybean)", "Glycine max", "Fabaceae", "warm_legume",
  dtm=[75, 90], harvest_days=14, germ_min=60, spacing=4, row=18, n_fix=50,
  succession=None, tips="Harvest when pods are plump and still bright green.")
P("runner_bean", "Bean (scarlet runner)", "Phaseolus coccineus", "Fabaceae", "warm_legume",
  dtm=[65, 75], harvest_days=60, heat_stress=85, grow_min=55, spacing=6, row=30,
  succession=None, tips="Prefers cooler summers; flowers fail to set in hot weather.")
P("peas_shell", "Pea (shelling)", "Pisum sativum", "Fabaceae", "cool_legume",
  dtm=[60, 70], harvest_days=21,
  companions=["carrot", "radish", "lettuce_leaf", "spinach", "turnip"],
  avoid=["onion_bulb", "garlic", "leek", "chives"],
  tips="Sow as soon as soil can be worked, 4–6 weeks before last frost. Inoculate seed "
       "if peas haven't grown in the bed before. Heat over 80°F ends the harvest.")
P("peas_snap", "Pea (snap/snow)", "Pisum sativum var. macrocarpon", "Fabaceae",
  "cool_legume", dtm=[55, 70], harvest_days=28,
  companions=["carrot", "radish", "lettuce_leaf", "spinach"],
  avoid=["onion_bulb", "garlic", "leek", "chives"],
  tips="Pick snow peas flat and snap peas plump. Fall crops: sow ~10 weeks before first frost.")
P("fava", "Fava bean", "Vicia faba", "Fabaceae", "cool_legume",
  frost="hardy", dtm=[80, 100], heat_max=75, spacing=6, row=24, n_fix=80,
  depth=2.0, tips="Doubles as a nitrogen-fixing cover crop; in mild winters sow in fall.")
P("peanut", "Peanut", "Arachis hypogaea", "Fabaceae", "warm_direct",
  feeder="fixer", n_demand=20, n_fix=50, residue_cn="low",
  dtm=[110, 150], harvest_days=14, germ_min=65, grow_min=65, kc=[0.4, 1.15, 0.6],
  spacing=8, row=30, depth=2.0, ph=[5.8, 6.5],
  tips="Needs 120+ frost-free days and loose, sandy soil the pegs can push into.")
P("sweet_pea", "Sweet pea (flower)", "Lathyrus odoratus", "Fabaceae", "cool_legume",
  category="flower", dtm=[60, 90], harvest_days=45, heat_max=80, spacing=6, row=12,
  tips="Fragrant cut flower — NOT edible. Pick often to keep blooms coming.")

# ------------------------------------------------------------------- brassicas
P("broccoli", "Broccoli", "Brassica oleracea var. italica", "Brassicaceae", "brassica_tp",
  dtm=[55, 80], harvest_days=30, heat_max=85, n_demand=150,
  companions=["onion_bulb", "dill", "chamomile", "beet", "lettuce_leaf", "nasturtium"],
  avoid=["tomato", "pole_bean", "strawberry"],
  tips="Harvest the main head while beads are tight; side shoots follow for weeks. Fall "
       "crops are sweeter and less buggy.")
P("cabbage", "Cabbage", "Brassica oleracea var. capitata", "Brassicaceae", "brassica_tp",
  dtm=[60, 90], harvest_days=21, heat_max=85, n_demand=150,
  companions=["onion_bulb", "dill", "thyme", "chamomile", "celery"],
  avoid=["tomato", "strawberry"],
  tips="Uneven watering splits heads. Row cover keeps cabbage worms off.")
P("cauliflower", "Cauliflower", "Brassica oleracea var. botrytis", "Brassicaceae",
  "brassica_tp", dtm=[55, 80], harvest_days=10, heat_max=80, n_demand=150,
  companions=["onion_bulb", "dill", "celery"], avoid=["tomato", "strawberry"],
  tips="The fussiest brassica: any check in growth (cold snap, drought) causes tiny "
       "'buttoned' heads. Tie leaves over white heads to blanch.")
P("brussels_sprouts", "Brussels sprouts", "Brassica oleracea var. gemmifera",
  "Brassicaceae", "brassica_tp", frost="very_hardy", dtm=[90, 110], harvest_days=45,
  heat_max=82, spacing=24, row=30, n_demand=150,
  tips="Time it to mature after the first frosts — frost sweetens the sprouts.")
P("kohlrabi", "Kohlrabi", "Brassica oleracea var. gongylodes", "Brassicaceae",
  "brassica_tp", method="either", prefer="direct", dtm_from="sow", dtm=[45, 60],
  harvest_days=14, spacing=6, row=12, n_demand=100, succession=21,
  tips="Harvest bulbs at 2–3 inches before they turn woody.")
P("kale", "Kale", "Brassica oleracea var. sabellica", "Brassicaceae", "brassica_tp",
  frost="very_hardy", dtm=[50, 65], harvest_days=120, heat_max=90, n_demand=120,
  spacing=15, row=18, companions=["beet", "onion_bulb", "dill"],
  tips="Pick lower leaves continuously. Survives to ~10°F and gets sweeter after frost.")
P("collards", "Collard greens", "Brassica oleracea var. viridis", "Brassicaceae",
  "brassica_tp", frost="very_hardy", dtm=[60, 80], harvest_days=120, heat_max=95,
  n_demand=120, spacing=18, row=24, tips="The most heat- and cold-tolerant brassica.")
P("napa_cabbage", "Napa / Chinese cabbage", "Brassica rapa subsp. pekinensis",
  "Brassicaceae", "brassica_tp", frost="semi", dtm=[50, 70], harvest_days=14,
  heat_max=75, n_demand=120, spacing=12, row=18,
  tips="Bolts after cold snaps in spring or long days — fall is the easier season.")
P("bok_choy", "Bok choy / Pak choi", "Brassica rapa subsp. chinensis", "Brassicaceae",
  "brassica_fast", dtm=[45, 60], heat_max=78, n_demand=80, spacing=8,
  tips="Baby bok choy is ready in ~30 days.")
P("radish", "Radish", "Raphanus sativus", "Brassicaceae", "brassica_fast",
  dtm=[22, 30], harvest_days=10, succession=10, spacing=2, row=6, n_demand=40,
  heat_max=82, feeder="light",
  companions=["peas_shell", "lettuce_leaf", "cucumber", "carrot", "spinach"],
  avoid=["hyssop"],
  tips="Sow small amounts every 10 days. Heat or crowding makes them pithy and hot.")
P("daikon", "Daikon radish", "Raphanus sativus var. longipinnatus", "Brassicaceae",
  "brassica_fast", dtm=[50, 70], harvest_days=30, heat_max=78, spacing=6, row=18,
  root_in=18, succession=None, n_demand=60,
  tips="Best sown in late summer for fall harvest; spring sowings often bolt.")
P("turnip", "Turnip", "Brassica rapa subsp. rapa", "Brassicaceae", "brassica_fast",
  dtm=[40, 60], harvest_days=21, spacing=4, row=12, n_demand=60, heat_max=82,
  tips="Greens and roots are both edible. Sweetest after light frost.")
P("rutabaga", "Rutabaga", "Brassica napus", "Brassicaceae", "brassica_fast",
  frost="very_hardy", dtm=[80, 100], harvest_days=45, spacing=6, row=18, n_demand=70,
  succession=None, root_in=18, tips="A fall crop: sow ~3 months before first frost.")
P("arugula", "Arugula", "Eruca vesicaria", "Brassicaceae", "brassica_fast",
  dtm=[30, 45], heat_max=75, spacing=4, row=8, n_demand=50,
  tips="Bolts quickly in heat; peppery flavor increases with warmth.")
P("mustard_greens", "Mustard greens", "Brassica juncea", "Brassicaceae", "brassica_fast",
  dtm=[35, 50], heat_max=80, spacing=6, row=12, n_demand=60,
  tips="Fast, easy fall green. Spicy when grown warm, mild when cool.")
P("mizuna", "Mizuna", "Brassica rapa var. japonica", "Brassicaceae", "brassica_fast",
  dtm=[35, 50], heat_max=80, spacing=6, row=12, n_demand=60,
  tips="Cut-and-come-again for salad mixes.")
P("tatsoi", "Tatsoi", "Brassica rapa var. rosularis", "Brassicaceae", "brassica_fast",
  frost="very_hardy", dtm=[45, 55], heat_max=78, spacing=6, row=12, n_demand=60,
  tips="Very cold hardy — great for winter cold frames.")
P("broccoli_raab", "Broccoli raab (rapini)", "Brassica rapa var. ruvo", "Brassicaceae",
  "brassica_fast", dtm=[40, 60], heat_max=75, spacing=4, row=12, n_demand=80,
  tips="Harvest when the first flower buds appear, before they open.")
P("gai_lan", "Chinese broccoli (gai lan)", "Brassica oleracea var. alboglabra",
  "Brassicaceae", "brassica_fast", dtm=[55, 65], heat_max=85, spacing=8, row=12,
  n_demand=100, tips="More heat tolerant than broccoli; harvest stalks just as buds form.")
P("sweet_alyssum", "Sweet alyssum", "Lobularia maritima", "Brassicaceae", "flower_cool",
  dtm=[40, 60], harvest_days=120, heat_max=None, spacing=6,
  tips="Low edging flower that feeds hoverflies and parasitic wasps (aphid predators).")

# ------------------------------------------------------------ beet/spinach family
P("spinach", "Spinach", "Spinacia oleracea", "Amaranthaceae", "leafy",
  frost="very_hardy", dtm=[40, 50], germ_min=35, germ_max=75, heat_max=78,
  spacing=4, n_demand=100, p=0.2,
  companions=["peas_shell", "radish", "strawberry"],
  tips="Bolts as days lengthen past ~14 hours. Overwinters under row cover in many zones.")
P("swiss_chard", "Swiss chard", "Beta vulgaris subsp. vulgaris", "Amaranthaceae", "leafy",
  frost="hardy", dtm=[50, 60], germ_min=50, germ_max=85, heat_max=None, harvest_days=120,
  method="either", prefer="direct", spacing=9, row=18, n_demand=90, succession=None,
  tips="Cut outer leaves and it keeps producing all season — heat and frost tolerant.")
P("beet", "Beet", "Beta vulgaris", "Amaranthaceae", "root",
  dtm=[50, 70], germ_min=50, spacing=3, n_demand=80, heat_max=85,
  companions=["onion_bulb", "lettuce_leaf", "cabbage", "kale"], avoid=["pole_bean"],
  tips="Each 'seed' is a cluster — thin to one plant per spot. Eat the thinnings.")
P("orach", "Orach (mountain spinach)", "Atriplex hortensis", "Amaranthaceae", "leafy",
  dtm=[40, 60], heat_max=88, spacing=8, n_demand=80,
  tips="Spinach substitute that tolerates more heat before bolting.")
P("amaranth", "Amaranth (greens/grain)", "Amaranthus spp.", "Amaranthaceae", "warm_direct",
  dtm=[30, 50], harvest_days=60, germ_min=65, spacing=8, row=18, depth=0.25,
  n_demand=60, feeder="medium", kc=[0.4, 1.0, 0.8], root_in=18,
  tips="Heat-loving summer green; grain types need ~90 days.")

# ------------------------------------------------------------------ daisy family
P("lettuce_leaf", "Lettuce (leaf/mesclun)", "Lactuca sativa", "Asteraceae", "leafy",
  dtm=[40, 50], heat_max=82, spacing=6, n_demand=80,
  companions=["carrot", "radish", "peas_shell", "chives", "onion_bulb"],
  tips="Needs light to germinate — barely cover seed. Seed won't sprout in soil over "
       "80°F; shade cloth stretches the season.")
P("lettuce_head", "Lettuce (head/romaine)", "Lactuca sativa", "Asteraceae", "leafy",
  dtm=[60, 75], heat_max=78, prefer="transplant", spacing=10, row=12, n_demand=90,
  companions=["carrot", "radish", "chives", "onion_bulb"],
  tips="Transplants mature 2–3 weeks sooner. Water consistently to prevent tipburn.")
P("endive", "Endive / Escarole", "Cichorium endivia", "Asteraceae", "leafy",
  dtm=[80, 95], heat_max=80, frost="hardy", spacing=10, n_demand=80,
  tips="Blanch for 2–3 weeks before harvest to reduce bitterness.")
P("radicchio", "Radicchio", "Cichorium intybus", "Asteraceae", "leafy",
  dtm=[75, 90], heat_max=80, frost="hardy", spacing=10, n_demand=80,
  tips="Heads up best in cool fall weather.")
P("salsify", "Salsify", "Tragopogon porrifolius", "Asteraceae", "root",
  dtm=[100, 120], frost="very_hardy", heat_max=None, spacing=3, root_in=24,
  succession=None, tips="Long season 'oyster plant' root; harvest after frost.")
P("sunflower", "Sunflower", "Helianthus annuus", "Asteraceae", "warm_direct",
  category="flower", dtm=[70, 100], harvest_days=30, germ_min=55, grow_min=55,
  spacing=18, row=30, n_demand=80, kc=[0.35, 1.0, 0.35],
  avoid=["potato", "pole_bean"],
  tips="Mildly allelopathic — keep seed heads and hulls out of vegetable beds.")
P("calendula", "Calendula", "Calendula officinalis", "Asteraceae", "flower_cool",
  dtm=[45, 60], harvest_days=90, heat_max=None, spacing=10,
  tips="Edible petals; attracts pollinators and aphid predators.")
P("zinnia", "Zinnia", "Zinnia elegans", "Asteraceae", "flower_warm",
  dtm=[60, 75], spacing=12, tips="Cut-and-come-again flower; pollinator magnet.")
P("cosmos", "Cosmos", "Cosmos bipinnatus", "Asteraceae", "flower_warm",
  dtm=[60, 80], spacing=12, n_demand=20,
  tips="Blooms best in lean soil; attracts beneficial insects.")
P("marigold", "Marigold", "Tagetes spp.", "Asteraceae", "flower_warm",
  dtm=[50, 60], prefer="transplant", spacing=10,
  tips="French marigolds suppress root-knot nematodes when grown as a dense cover.")
P("bachelors_button", "Bachelor's button", "Centaurea cyanus", "Asteraceae", "flower_cool",
  frost="hardy", dtm=[60, 70], heat_max=None, spacing=9,
  tips="Sow in fall or early spring; extrafloral nectar feeds beneficials.")
P("chamomile", "Chamomile (German)", "Matricaria chamomilla", "Asteraceae", "herb_cool",
  dtm=[60, 70], harvest_days=60, germ_min=55, depth=0.0, spacing=8,
  tips="Surface-sow; seed needs light to germinate. Pick flowers when fully open.")
P("stevia", "Stevia", "Stevia rebaudiana", "Asteraceae", "herb_warm",
  dtm=[70, 90], prefer="transplant", indoor_weeks=[8, 10], germ_min=70, spacing=18,
  tips="Sweetest leaves just before flowering; overwinter indoors in cold zones.")

# --------------------------------------------------------------- carrot family
P("carrot", "Carrot", "Daucus carota subsp. sativus", "Apiaceae", "root",
  dtm=[60, 80], germ_days=[10, 21], spacing=2, n_demand=70,
  companions=["onion_bulb", "leek", "lettuce_leaf", "peas_shell", "tomato", "chives"],
  avoid=["dill", "parsnip"],
  tips="Keep the seedbed moist for up to 3 weeks until emergence (a board or burlap "
       "helps). Loose, stone-free soil prevents forking. Fall carrots sweeten after frost.")
P("parsnip", "Parsnip", "Pastinaca sativa", "Apiaceae", "root",
  frost="very_hardy", dtm=[110, 130], germ_days=[14, 28], spacing=4, heat_max=85,
  root_in=24, succession=None,
  tips="Always sow fresh seed. Harvest after several hard frosts for sweetness.")
P("celery", "Celery", "Apium graveolens var. dulce", "Apiaceae", "leafy",
  method="transplant", prefer="transplant", indoor_weeks=[10, 12], dtm_from="transplant",
  dtm=[85, 120], harvest_days=30, germ_min=50, germ_max=75, germ_days=[14, 21],
  grow_min=50, heat_max=85, frost="semi", feeder="heavy", n_demand=150,
  kc=[0.7, 1.05, 1.0], p=0.2, spacing=8, succession=None,
  companions=["cabbage", "leek", "bush_bean"],
  tips="Constant moisture is everything. More than 10 nights below 55°F after "
       "transplant can trigger bolting.")
P("celeriac", "Celeriac", "Apium graveolens var. rapaceum", "Apiaceae", "leafy",
  method="transplant", prefer="transplant", indoor_weeks=[10, 12], dtm_from="transplant",
  dtm=[100, 120], harvest_days=30, germ_min=50, germ_max=75, germ_days=[14, 21],
  grow_min=45, heat_max=88, frost="hardy", feeder="heavy", n_demand=120,
  kc=[0.7, 1.05, 1.0], p=0.2, spacing=8, succession=None,
  tips="Remove side roots and lower leaves as the bulb swells.")
P("parsley", "Parsley", "Petroselinum crispum", "Apiaceae", "herb_cool",
  lifecycle="biennial", frost="hardy", method="either", prefer="transplant",
  indoor_weeks=[8, 10], dtm=[70, 90], harvest_days=150, germ_days=[14, 28],
  heat_max=None, succession=None, spacing=8,
  companions=["tomato", "asparagus", "carrot"],
  tips="Soak seed overnight; it is slow to germinate. Host plant for swallowtail caterpillars.")
P("cilantro", "Cilantro / Coriander", "Coriandrum sativum", "Apiaceae", "herb_cool",
  dtm=[45, 70], heat_max=80, germ_max=85, succession=21, spacing=4,
  tips="Bolts fast in heat — sow every 3 weeks in spring and fall. Let some go to seed "
       "for coriander.")
P("dill", "Dill", "Anethum graveolens", "Apiaceae", "herb_cool",
  dtm=[40, 60], harvest_days=60, germ_min=60, heat_max=None, spacing=8,
  companions=["cabbage", "cucumber", "lettuce_leaf", "onion_bulb"],
  avoid=["carrot", "tomato"],
  tips="Direct sow; resents transplanting. Flowers draw beneficial wasps.")
P("fennel_bulb", "Fennel (Florence/bulb)", "Foeniculum vulgare var. azoricum", "Apiaceae",
  "herb_cool", category="vegetable", method="either", prefer="direct", indoor_weeks=[4, 5],
  dtm=[65, 90], harvest_days=21, heat_max=85, spacing=10, n_demand=80, succession=None,
  avoid=["tomato", "bush_bean", "pole_bean", "pepper_sweet", "kohlrabi", "cilantro", "dill"],
  tips="Allelopathic — give it its own corner. Bolts if transplanted roughly or stressed.")
P("chervil", "Chervil", "Anthriscus cerefolium", "Apiaceae", "herb_cool",
  dtm=[40, 60], heat_max=75, spacing=6, tips="Prefers part shade and cool weather.")

# -------------------------------------------------------------------- alliums
P("onion_bulb", "Onion (from seed/transplants)", "Allium cepa", "Amaryllidaceae", "allium",
  dtm=[90, 120],
  companions=["carrot", "beet", "lettuce_leaf", "cabbage", "tomato", "chamomile"],
  avoid=["bush_bean", "pole_bean", "peas_shell", "peas_snap", "sage"],
  tips="Pick day-length type by latitude: long-day north of ~37°N, intermediate 32–38°N, "
       "short-day in the South. Bulbing is triggered by day length, not plant size.")
P("onion_sets", "Onion (sets)", "Allium cepa", "Amaryllidaceae", "allium",
  method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow", dtm=[80, 100],
  germ_min=40, germ_days=[7, 14],
  avoid=["bush_bean", "pole_bean", "peas_shell"],
  tips="Plant sets 2–4 weeks before last frost, 1 inch deep. Choose sets smaller than a "
       "dime — big ones bolt.")
P("leek", "Leek", "Allium ampeloprasum", "Amaryllidaceae", "allium",
  frost="very_hardy", indoor_weeks=[10, 12], dtm=[90, 130], harvest_days=90,
  n_demand=120, spacing=6, companions=["carrot", "celery"],
  tips="Plant transplants in a 6-inch trench and hill up for long white shanks.")
P("scallion", "Scallion / Green onion", "Allium fistulosum", "Amaryllidaceae", "allium",
  method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow", dtm=[60, 70],
  succession=21, spacing=1, n_demand=60, germ_min=45,
  tips="Sow thickly in bands every 3 weeks.")
P("garlic", "Garlic", "Allium sativum", "Amaryllidaceae", "allium",
  frost="very_hardy", method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
  dtm=[210, 270], harvest_days=14, spacing=6, depth=2.0, n_demand=120,
  special={"plant": ("fff", 7, "fff", 35), "harvest": ("lsf+1", 50, "lsf+1", 75),
           "kind": "overwinter"},
  companions=["tomato", "carrot", "beet", "strawberry"],
  avoid=["bush_bean", "pole_bean", "peas_shell"],
  tips="Plant cloves 2–5 weeks after the first fall frost so roots grow before the ground "
       "freezes; mulch heavily. Cut hardneck scapes in June. Harvest when the lower third "
       "of the leaves are brown.")
P("shallot", "Shallot", "Allium cepa var. aggregatum", "Amaryllidaceae", "allium",
  frost="very_hardy", method="direct", prefer="direct", indoor_weeks=None, dtm_from="sow",
  dtm=[180, 240], harvest_days=14, spacing=6, depth=1.0, n_demand=90,
  special={"plant": ("fff", 0, "fff", 30), "harvest": ("lsf+1", 40, "lsf+1", 65),
           "kind": "overwinter"},
  avoid=["bush_bean", "pole_bean", "peas_shell"],
  tips="Fall-planted bulbs divide into clusters of 5–10. Can also be spring planted.")
P("chives", "Chives", "Allium schoenoprasum", "Amaryllidaceae", "herb_perennial",
  spacing=8, companions=["carrot", "tomato", "lettuce_leaf"],
  avoid=["bush_bean", "peas_shell"],
  tips="Divide clumps every 3 years. Flowers are edible and loved by bees.")
P("garlic_chives", "Garlic chives", "Allium tuberosum", "Amaryllidaceae", "herb_perennial",
  spacing=8, tips="Deadhead before seed sets or it self-sows aggressively.")

# --------------------------------------------------------------------- grasses
P("sweet_corn", "Sweet corn", "Zea mays var. saccharata", "Poaceae", "warm_direct",
  dtm=[65, 90], harvest_days=10, germ_min=55, germ_days=[7, 10], grow_min=58,
  heat_stress=95, succession=14, spacing=10, row=30, kc=[0.3, 1.15, 1.05], root_in=30,
  feeder="heavy", n_demand=150, residue_frac=0.5, residue_cn="high",
  companions=["pole_bean", "winter_squash", "pumpkin", "cucumber"],
  avoid=["tomato"],
  tips="Plant in blocks of at least 4 rows for pollination. Supersweet (sh2) types need "
       "65°F soil and isolation from other types. Side-dress nitrogen at knee height.")
P("popcorn", "Popcorn / Flour corn", "Zea mays", "Poaceae", "warm_direct",
  dtm=[90, 120], harvest_days=21, germ_min=55, grow_min=58, spacing=10, row=30,
  kc=[0.3, 1.15, 0.6], root_in=30, feeder="heavy", n_demand=140,
  residue_frac=0.5, residue_cn="high", succession=None,
  tips="Let ears dry on the stalk; isolate from sweet corn.")
P("lemongrass", "Lemongrass", "Cymbopogon citratus", "Poaceae", "herb_warm",
  dtm=[75, 100], indoor_weeks=[8, 10], prefer="transplant", spacing=24, n_demand=80,
  tips="Root grocery-store stalks in water for free transplants; overwinter indoors.")

# -------------------------------------------------------------- misc. warm crops
P("okra", "Okra", "Abelmoschus esculentus", "Malvaceae", "warm_direct",
  dtm=[50, 65], harvest_days=75, germ_min=65, germ_days=[7, 14], grow_min=65,
  heat_stress=105, method="either", indoor_weeks=[4, 6], spacing=12, row=36,
  n_demand=90, kc=[0.5, 1.0, 0.8],
  tips="Soak seed overnight. Pick pods at 2–4 inches every other day.")
P("sweet_potato", "Sweet potato", "Ipomoea batatas", "Convolvulaceae", "warm_direct",
  method="transplant", prefer="transplant", indoor_weeks=[6, 8], dtm_from="transplant",
  dtm=[90, 120], harvest_days=14, germ_min=65, grow_min=65, spacing=12, row=36,
  kc=[0.5, 1.15, 0.65], feeder="light", n_demand=60, residue_frac=0.3,
  tips="Plant rooted slips 2–3 weeks after last frost into warm soil. Too much nitrogen "
       "gives vines, not roots. Harvest before soil drops below 55°F; cure warm and humid.")
P("malabar_spinach", "Malabar spinach", "Basella alba", "Basellaceae", "warm_direct",
  method="either", indoor_weeks=[4, 6], dtm=[60, 70], harvest_days=90, germ_min=65,
  germ_days=[10, 21], spacing=12, row=24, feeder="medium", n_demand=80,
  tips="Heat-loving climbing spinach substitute; needs a trellis.")
P("nz_spinach", "New Zealand spinach", "Tetragonia tetragonioides", "Aizoaceae",
  "warm_direct", frost="semi", dtm=[55, 70], harvest_days=90, germ_min=60,
  germ_days=[10, 21], spacing=12, row=24, feeder="medium", n_demand=80,
  tips="Soak seed 24 hours. Summer spinach substitute that never bolts.")
P("ginger", "Ginger", "Zingiber officinale", "Zingiberaceae", "warm_direct",
  method="transplant", prefer="transplant", indoor_weeks=[6, 8], dtm_from="transplant",
  dtm=[180, 240], harvest_days=14, germ_min=70, grow_min=65, spacing=8, row=12,
  feeder="medium", n_demand=80, sun="part",
  tips="Pre-sprout rhizomes indoors. Needs a long warm season; harvest baby ginger in fall.")

# ---------------------------------------------------------------------- herbs
P("basil", "Basil", "Ocimum basilicum", "Lamiaceae", "herb_warm",
  dtm=[60, 75], succession=30, diseases=["downy_mildew"],
  companions=["tomato", "pepper_sweet", "oregano"], avoid=["sage"],
  tips="Damaged by temperatures below 50°F — don't rush it out. Pinch flower buds for "
       "more leaves.")
P("summer_savory", "Summer savory", "Satureja hortensis", "Lamiaceae", "herb_warm",
  dtm=[60, 70], method="direct", prefer="direct", spacing=8,
  companions=["bush_bean"], tips="Classic bean companion; surface sow.")
P("marjoram", "Marjoram", "Origanum majorana", "Lamiaceae", "herb_warm",
  dtm=[70, 90], indoor_weeks=[6, 8], spacing=8,
  tips="Tender perennial grown as an annual north of zone 9.")
P("borage", "Borage", "Borago officinalis", "Boraginaceae", "herb_cool",
  frost="semi", dtm=[50, 60], harvest_days=90, heat_max=None, germ_min=55, spacing=12,
  companions=["tomato", "strawberry", "summer_squash"],
  tips="Bee magnet with edible flowers; self-sows freely.")
P("oregano", "Oregano", "Origanum vulgare", "Lamiaceae", "herb_perennial", spacing=12,
  tips="Harvest just before flowering for strongest flavor.")
P("thyme", "Thyme", "Thymus vulgaris", "Lamiaceae", "herb_perennial", spacing=10,
  kc=[0.4, 0.7, 0.6], tips="Needs sharp drainage; prune after flowering.")
P("sage", "Sage", "Salvia officinalis", "Lamiaceae", "herb_perennial", spacing=18,
  kc=[0.4, 0.7, 0.6], avoid=["cucumber", "onion_bulb"],
  tips="Replace woody plants every 4–5 years.")
P("rosemary", "Rosemary", "Salvia rosmarinus", "Lamiaceae", "herb_perennial",
  frost="hardy", spacing=24, kc=[0.4, 0.7, 0.6],
  tips="Hardy only to zone 7 (some cultivars zone 6). Grow in a pot north of that.")
P("mint", "Mint", "Mentha spp.", "Lamiaceae", "herb_perennial", spacing=18,
  kc=[0.6, 1.0, 0.9], sun="part",
  tips="Invasive runners — grow in a container or sunken pot.")
P("lemon_balm", "Lemon balm", "Melissa officinalis", "Lamiaceae", "herb_perennial",
  spacing=18, sun="part", tips="Cut back after flowering to prevent self-seeding.")
P("catnip", "Catnip", "Nepeta cataria", "Lamiaceae", "herb_perennial", spacing=18,
  tips="Deters flea beetles; attracts cats.")
P("lavender", "Lavender", "Lavandula angustifolia", "Lamiaceae", "herb_perennial",
  spacing=24, kc=[0.3, 0.6, 0.5], ph=[6.5, 8.0],
  tips="Lean, well-drained, alkaline soil. Never prune into old wood.")
P("hyssop", "Hyssop", "Hyssopus officinalis", "Lamiaceae", "herb_perennial", spacing=12,
  tips="Pollinator plant; attracts bees and butterflies.")
P("tarragon", "Tarragon (French)", "Artemisia dracunculus", "Asteraceae", "herb_perennial",
  spacing=24, tips="Propagated by division only — French tarragon sets no viable seed.")
P("sorrel", "Sorrel", "Rumex acetosa", "Polygonaceae", "herb_perennial",
  category="vegetable", special={"plant": ("lsf", -21, "lsf", 14),
                                 "harvest": ("lsf", 0, "fff", 0),
                                 "kind": "perennial", "first_harvest_year": 1},
  spacing=12, tips="Lemony perennial green; cut flower stalks to keep leaves tender.")

# ---------------------------------------------------------- perennial vegetables
P("asparagus", "Asparagus", "Asparagus officinalis", "Asparagaceae", "perennial_veg",
  n_demand=100, spacing=18, depth=6.0, ph=[6.5, 7.5],
  special={"plant": ("lsf", -42, "lsf", -7), "harvest": ("lsf", -14, "lsf", 42),
           "kind": "perennial", "first_harvest_year": 3},
  companions=["tomato", "parsley", "basil"],
  tips="Plant crowns in a trench 6 inches deep. No harvest year 1, two weeks year 2, "
       "full 6–8 week harvest from year 3. Beds produce for 20 years.")
P("rhubarb", "Rhubarb", "Rheum × hybridum", "Polygonaceae", "perennial_veg",
  n_demand=90, spacing=36,
  special={"plant": ("lsf", -42, "lsf", -7), "harvest": ("lsf", -7, "lsf", 60),
           "kind": "perennial", "first_harvest_year": 2},
  tips="Leaves are toxic — eat stalks only. Needs winter chilling (zone 3–8).")
P("artichoke", "Globe artichoke", "Cynara cardunculus var. scolymus", "Asteraceae",
  "perennial_veg", frost="hardy", n_demand=100, spacing=36,
  special={"plant": ("lsf", 0, "lsf", 21), "harvest": ("lsf", 60, "lsf", 120),
           "kind": "perennial", "first_harvest_year": 1},
  tips="Perennial in zones 7–11; elsewhere grow 'Imperial Star' as an annual and give "
       "transplants 10 days of temperatures below 50°F to trigger budding.")
P("horseradish", "Horseradish", "Armoracia rusticana", "Brassicaceae", "perennial_veg",
  n_demand=60, spacing=24,
  special={"plant": ("lsf", -28, "lsf", 0), "harvest": ("fff", 0, "fff", 60),
           "kind": "perennial", "first_harvest_year": 1},
  tips="Spreads aggressively — any root piece regrows. Harvest after frost.")
P("jerusalem_artichoke", "Jerusalem artichoke (sunchoke)", "Helianthus tuberosus",
  "Asteraceae", "perennial_veg", n_demand=60, spacing=18,
  special={"plant": ("lsf", -28, "lsf", 14), "harvest": ("fff", 0, "fff", 90),
           "kind": "perennial", "first_harvest_year": 1},
  tips="8-ft tall and invasive — plant where it can stay forever.")

# ------------------------------------------------------------------------ fruit
P("strawberry", "Strawberry", "Fragaria × ananassa", "Rosaceae", "fruit",
  spacing=12, row=36, kc=[0.4, 0.85, 0.75], root_in=12, p=0.2, n_demand=70,
  ph=[5.5, 6.5],
  special={"plant": ("lsf", -28, "lsf", 7), "harvest": ("lsf", 25, "lsf", 60),
           "kind": "perennial", "first_harvest_year": 2},
  companions=["borage", "spinach", "garlic", "thyme"],
  avoid=["cabbage", "broccoli", "cauliflower"],
  tips="Pinch first-year flowers on June-bearers. Renew the bed every 3–4 years in a new "
       "spot (verticillium). Everbearers also fruit in late summer.")
P("raspberry", "Raspberry", "Rubus idaeus", "Rosaceae", "fruit", spacing=24, row=96,
  n_demand=60,
  special={"plant": ("lsf", -42, "lsf", 0), "harvest": ("lsf", 55, "lsf", 100),
           "kind": "perennial", "first_harvest_year": 2},
  avoid=["tomato", "potato", "eggplant"],
  tips="Don't plant where nightshades grew in the last 3 years (verticillium wilt). "
       "Fall-bearing types also fruit Aug–frost.")
P("blackberry", "Blackberry", "Rubus spp.", "Rosaceae", "fruit", spacing=48, row=96,
  special={"plant": ("lsf", -42, "lsf", 0), "harvest": ("lsf", 65, "lsf", 110),
           "kind": "perennial", "first_harvest_year": 2},
  tips="Canes fruit in their second year, then die — remove them after harvest.")
P("blueberry", "Blueberry", "Vaccinium corymbosum", "Ericaceae", "fruit",
  spacing=60, row=96, ph=[4.5, 5.5], root_in=18, p=0.4, n_demand=40,
  special={"plant": ("lsf", -42, "lsf", 0), "harvest": ("lsf", 50, "lsf", 100),
           "kind": "perennial", "first_harvest_year": 3},
  tips="Needs acid soil (pH 4.5–5.5): acidify with elemental sulfur a season ahead. Use "
       "ammonium-based fertilizer, never nitrate. Plant two varieties for pollination.")
P("grape", "Grape", "Vitis spp.", "Vitaceae", "fruit", spacing=96, row=96, n_demand=40,
  kc=[0.3, 0.7, 0.45],
  special={"plant": ("lsf", -42, "lsf", 0), "harvest": ("fff", -60, "fff", -7),
           "kind": "perennial", "first_harvest_year": 3},
  tips="Prune hard in late winter — fruit forms on this year's shoots.")
P("apple", "Apple", "Malus domestica", "Rosaceae", "fruit", spacing=144, row=180,
  kc=[0.45, 0.95, 0.7], root_in=36,
  special={"plant": ("lsf", -42, "lsf", -7), "harvest": ("fff", -60, "fff", 14),
           "kind": "perennial", "first_harvest_year": 4},
  tips="Most need a different apple/crabapple nearby for pollination. Check chill hours.")
P("pear", "Pear", "Pyrus communis", "Rosaceae", "fruit", spacing=144, row=180,
  kc=[0.45, 0.95, 0.7], root_in=36,
  special={"plant": ("lsf", -42, "lsf", -7), "harvest": ("fff", -75, "fff", -7),
           "kind": "perennial", "first_harvest_year": 4},
  tips="Pick European pears hard-mature and ripen indoors.")
P("peach", "Peach / Nectarine", "Prunus persica", "Rosaceae", "fruit", spacing=144,
  row=180, kc=[0.45, 0.9, 0.65], root_in=36,
  special={"plant": ("lsf", -42, "lsf", -7), "harvest": ("lsf", 75, "lsf", 130),
           "kind": "perennial", "first_harvest_year": 3},
  tips="Early bloom makes peaches frost-prone; plant on a slope, not in a frost pocket.")
P("cherry", "Cherry", "Prunus avium / P. cerasus", "Rosaceae", "fruit", spacing=144,
  row=180, kc=[0.45, 0.95, 0.7], root_in=36,
  special={"plant": ("lsf", -42, "lsf", -7), "harvest": ("lsf", 30, "lsf", 65),
           "kind": "perennial", "first_harvest_year": 4},
  tips="Tart cherries are self-fertile and hardier than sweet cherries.")
P("plum", "Plum", "Prunus domestica / P. salicina", "Rosaceae", "fruit", spacing=144,
  row=180, kc=[0.45, 0.95, 0.7], root_in=36,
  special={"plant": ("lsf", -42, "lsf", -7), "harvest": ("lsf", 60, "lsf", 120),
           "kind": "perennial", "first_harvest_year": 4},
  tips="Japanese plums bloom early and need a pollinator; European types are hardier.")
P("fig", "Fig", "Ficus carica", "Moraceae", "fruit", frost="hardy", spacing=120,
  row=120, kc=[0.4, 0.85, 0.7],
  special={"plant": ("lsf", 0, "lsf", 28), "harvest": ("lsf", 80, "fff", 0),
           "kind": "perennial", "first_harvest_year": 2},
  tips="Hardy to zone 7 (6 with protection). Elsewhere grow in a large pot and overwinter "
       "in a garage.")

# ----------------------------------------------------------------- more flowers
P("nasturtium", "Nasturtium", "Tropaeolum majus", "Tropaeolaceae", "flower_warm",
  dtm=[50, 60], method="direct", prefer="direct", germ_min=55, depth=0.5, n_demand=20,
  tips="Edible leaves and flowers; trap crop that lures aphids away from vegetables. "
       "Rich soil gives leaves instead of flowers.")
P("snapdragon", "Snapdragon", "Antirrhinum majus", "Plantaginaceae", "flower_cool",
  method="transplant", prefer="transplant", indoor_weeks=[8, 10], dtm_from="transplant",
  dtm=[60, 80], frost="hardy",
  tips="Cool-season cut flower; pinch once for bushier plants.")

# ---------------------------------------------------------------- cover crops
P("cereal_rye", "Cereal rye (winter rye)", "Secale cereale", "Poaceae", "cover_winter",
  special={"plant": ("fff", -28, "fff", 28), "harvest": ("lsf+1", -14, "lsf+1", 21),
           "kind": "overwinter"},
  n_demand=50, residue_cn="high",
  tips="The hardiest cover crop and best nitrogen 'catch crop' — it soaks up leftover "
       "nitrate before winter rains leach it. Terminate at least 3 weeks before planting "
       "small seeds (allelopathic). Mature rye ties up nitrogen as it decomposes.")
P("winter_wheat", "Winter wheat (cover)", "Triticum aestivum", "Poaceae", "cover_winter",
  special={"plant": ("fff", -21, "fff", 21), "harvest": ("lsf+1", -14, "lsf+1", 21),
           "kind": "overwinter"},
  n_demand=40, residue_cn="high", tips="Easier to terminate than rye; less allelopathic.")
P("barley", "Barley (cover)", "Hordeum vulgare", "Poaceae", "cover_winter",
  frost="hardy",
  special={"plant": ("fff", -56, "fff", -14), "harvest": ("lsf+1", -21, "lsf+1", 14),
           "kind": "overwinter"},
  n_demand=40, residue_cn="medium", tips="Hardy to about zone 6; tolerates dry, salty soils.")
P("oats", "Oats (winter-killed cover)", "Avena sativa", "Poaceae", "cover_winter",
  frost="hardy",
  special={"plant": ("fff", -70, "fff", -35), "harvest": ("fff", 14, "fff", 45),
           "kind": "winterkill"},
  n_demand=40, residue_cn="medium",
  tips="Winter-kills below ~15°F, leaving a mulch you can plant early crops straight "
       "into. Pairs well with peas.")
P("hairy_vetch", "Hairy vetch", "Vicia villosa", "Fabaceae", "cover_winter",
  feeder="fixer", n_demand=10, n_fix=120, residue_cn="low",
  special={"plant": ("fff", -45, "fff", -14), "harvest": ("lsf+1", 7, "lsf+1", 30),
           "kind": "overwinter"},
  tips="Top nitrogen producer (often 100–150 lb N/acre). Terminate at early bloom by "
       "cutting at the soil line; plant tomatoes into the mulch.")
P("crimson_clover", "Crimson clover", "Trifolium incarnatum", "Fabaceae", "cover_winter",
  frost="hardy", feeder="fixer", n_demand=10, n_fix=90, residue_cn="low",
  special={"plant": ("fff", -56, "fff", -28), "harvest": ("lsf+1", -7, "lsf+1", 21),
           "kind": "overwinter"},
  tips="Beautiful and fast; reliably hardy to zone 6. Terminate at early bloom.")
P("red_clover", "Red clover", "Trifolium pratense", "Fabaceae", "cover_winter",
  feeder="fixer", n_demand=10, n_fix=90, residue_cn="low",
  special={"plant": ("fff", -60, "fff", -35), "harvest": ("lsf+1", 0, "lsf+1", 35),
           "kind": "overwinter"},
  tips="Can be frost-seeded into early spring crops or sown late summer.")
P("white_clover", "White clover (living mulch)", "Trifolium repens", "Fabaceae",
  "cover_winter", feeder="fixer", n_demand=10, n_fix=80, residue_cn="low",
  special={"plant": ("lsf", -28, "lsf", 14), "harvest": ("lsf", 30, "fff", 0),
           "kind": "perennial", "first_harvest_year": 1},
  tips="Low perennial for paths and orchard floors; tolerates foot traffic.")
P("winter_pea", "Austrian winter pea", "Pisum sativum subsp. arvense", "Fabaceae",
  "cover_winter", frost="hardy", feeder="fixer", n_demand=10, n_fix=100, residue_cn="low",
  special={"plant": ("fff", -42, "fff", -14), "harvest": ("lsf+1", -7, "lsf+1", 14),
           "kind": "overwinter"},
  tips="Fast-decomposing, high-N residue. Survives to about zone 6 with snow cover.")
P("tillage_radish", "Tillage / forage radish", "Raphanus sativus var. longipinnatus",
  "Brassicaceae", "cover_winter", frost="hardy", n_demand=60, residue_cn="low",
  special={"plant": ("fff", -60, "fff", -35), "harvest": ("fff", 14, "fff", 45),
           "kind": "winterkill"},
  tips="Deep taproot breaks compaction and scavenges nitrogen; rots away over winter, "
       "releasing it early in spring. Counts as a brassica for rotation.")
P("buckwheat", "Buckwheat", "Fagopyrum esculentum", "Polygonaceae", "cover_summer",
  dtm=[35, 45], germ_min=50, n_demand=20, residue_cn="low",
  tips="Smothers weeds and feeds pollinators in 6 weeks. Mow at first seed set or it "
       "reseeds. Mobilizes phosphorus.")
P("sorghum_sudan", "Sorghum-sudangrass", "Sorghum × drummondii", "Poaceae", "cover_summer",
  dtm=[60, 80], germ_min=65, n_demand=60, residue_cn="high",
  tips="Huge biomass and root mass in summer heat; mow at 3–4 ft to encourage regrowth.")
P("sunn_hemp", "Sunn hemp", "Crotalaria juncea", "Fabaceae", "cover_summer",
  dtm=[60, 90], germ_min=65, feeder="fixer", n_demand=10, n_fix=100,
  tips="Fast summer legume — up to 120 lb N/acre in 60–90 days.")
P("cowpea_cover", "Cowpea (cover crop)", "Vigna unguiculata", "Fabaceae", "cover_summer",
  dtm=[60, 70], germ_min=65, feeder="fixer", n_demand=10, n_fix=70,
  tips="Drought-tolerant summer legume cover; mow at flowering.")
P("mustard_cover", "Mustard (biofumigant cover)", "Brassica juncea", "Brassicaceae",
  "brassica_fast", category="cover", dtm=[40, 60], harvest_days=7, n_demand=60,
  residue_frac=1.0, succession=None,
  tips="Chop and incorporate at flowering, then water in to release biofumigant "
       "compounds. Counts as a brassica for rotation.")
P("phacelia", "Phacelia", "Phacelia tanacetifolia", "Boraginaceae", "flower_cool",
  category="cover", dtm=[45, 60], harvest_days=14, n_demand=30, residue_frac=1.0,
  residue_cn="low", tips="Superb bee forage; a non-family cover that fits any rotation.")
P("berseem_clover", "Berseem clover", "Trifolium alexandrinum", "Fabaceae", "cool_legume",
  category="cover", dtm=[50, 70], harvest_days=14, n_fix=80, n_demand=10,
  residue_frac=1.0, heat_max=None,
  tips="Fast annual clover for spring or fall; winter-kills below ~20°F.")

# ------------------------------------------------------- dry legumes (pulses)
P("dry_bean", "Bean (dry: pinto, black, kidney…)", "Phaseolus vulgaris", "Fabaceae",
  "warm_legume", dtm=[85, 105], harvest_days=21, succession=None, spacing=4, row=24,
  n_fix=40, heat_stress=95, kc=[0.4, 1.15, 0.35],
  companions=["sweet_corn", "popcorn", "winter_squash", "carrot", "marigold"],
  avoid=["onion_bulb", "garlic", "leek", "chives", "fennel_bulb"],
  tips="Grown like bush snap beans, but leave the pods on the plant until they are dry and "
       "papery and the beans rattle. If rain threatens at the end, pull whole plants and "
       "finish drying them under cover. Thresh, then freeze the dried beans for 48 hours to "
       "kill weevils.")
P("chickpea", "Chickpea (garbanzo)", "Cicer arietinum", "Fabaceae", "cool_legume",
  frost="semi", dtm=[90, 110], harvest_days=14, germ_min=45, germ_max=85, heat_max=92,
  spacing=4, row=18, n_fix=40, kc=[0.4, 1.0, 0.35], p=0.5,
  tips="Likes dry summers: wet weather while pods fill causes blight. Harvest when plants "
       "turn tan and pods rattle; each pod holds 1–2 seeds, so yields are modest.")
P("lentil", "Lentil", "Lens culinaris", "Fabaceae", "cool_legume",
  dtm=[80, 110], harvest_days=14, heat_max=90, spacing=1, row=12, n_fix=40,
  kc=[0.4, 1.1, 0.3], p=0.5,
  tips="A dryland crop: sow in early spring, harvest when the lower pods turn brown and "
       "rattle. Tiny yields per plant — best as a fun patch rather than a pantry supply.")

# ------------------------------------------------------- subtropical fruit
P("avocado", "Avocado", "Persea americana", "Lauraceae", "fruit", frost="tender",
  spacing=240, row=240, kc=[0.6, 0.85, 0.75],
  special={"plant": ("lsf", 14, "lsf", 60), "harvest": ("fff", -60, "fff", 90),
           "kind": "perennial", "first_harvest_year": 4},
  tips="Needs near frost-free winters (Mexican types survive ~20°F, most others ~30°F) "
       "and perfect drainage — root rot kills avocados in wet soil.")
P("lemon", "Lemon / Lime (citrus)", "Citrus × limon", "Rutaceae", "fruit", frost="semi",
  spacing=144, row=144, kc=[0.6, 0.7, 0.7], ph=[6.0, 7.0],
  special={"plant": ("lsf", 7, "lsf", 60), "harvest": ("fff", 0, "fff", 120),
           "kind": "perennial", "first_harvest_year": 3},
  tips="Meyer lemons are the hardiest (to ~25°F) and do well in a large pot you bring "
       "inside for winter. Limes are the most cold-tender citrus.")
P("orange", "Orange / Mandarin", "Citrus × sinensis", "Rutaceae", "fruit", frost="semi",
  spacing=180, row=180, kc=[0.6, 0.7, 0.7], ph=[6.0, 7.0],
  special={"plant": ("lsf", 7, "lsf", 60), "harvest": ("fff", 30, "fff", 150),
           "kind": "perennial", "first_harvest_year": 3},
  tips="Satsuma mandarins are the most cold-hardy (to ~20°F). Fruit sweetens on the tree.")
P("olive", "Olive", "Olea europaea", "Oleaceae", "fruit", frost="hardy",
  spacing=240, row=240, kc=[0.5, 0.65, 0.65], ph=[6.5, 8.0],
  special={"plant": ("lsf", 0, "lsf", 45), "harvest": ("fff", -30, "fff", 45),
           "kind": "perennial", "first_harvest_year": 4},
  tips="Needs long hot summers and mild winters (hardy to ~15°F). Raw olives must be "
       "cured before eating.")
P("pomegranate", "Pomegranate", "Punica granatum", "Lythraceae", "fruit", frost="hardy",
  spacing=144, row=144, kc=[0.4, 0.7, 0.6],
  special={"plant": ("lsf", 0, "lsf", 45), "harvest": ("fff", -45, "fff", 0),
           "kind": "perennial", "first_harvest_year": 3},
  tips="Loves heat and tolerates drought and alkaline soil; Russian varieties survive ~5°F.")
P("banana", "Banana", "Musa acuminata", "Musaceae", "fruit", frost="tender",
  spacing=120, row=120, kc=[0.6, 1.1, 1.0], root_in=24,
  special={"plant": ("lsf", 14, "lsf", 60), "harvest": ("lsf", 300, "lsf", 400),
           "kind": "perennial", "first_harvest_year": 2},
  tips="Fruit needs 10–15 frost-free months; in cooler zones plants grow but rarely ripen.")
P("mango", "Mango", "Mangifera indica", "Anacardiaceae", "fruit", frost="tender",
  spacing=300, row=300, kc=[0.5, 0.8, 0.7],
  special={"plant": ("lsf", 14, "lsf", 60), "harvest": ("lsf", 120, "lsf", 200),
           "kind": "perennial", "first_harvest_year": 4},
  tips="Tropical: damaged below ~30°F and needs a dry spell to flower.")

# ---------------------------------------------------- climate & soil fit
ZONES = {
    "asparagus": (3, 8), "rhubarb": (3, 8), "artichoke": (7, 11), "horseradish": (3, 9),
    "jerusalem_artichoke": (3, 9), "strawberry": (3, 10), "raspberry": (3, 9),
    "blackberry": (5, 10), "blueberry": (4, 7.5), "grape": (4, 10), "apple": (3, 8.5),
    "pear": (4, 9), "peach": (5, 9), "cherry": (4, 8), "plum": (4, 9), "fig": (7, 11),
    "oregano": (5, 10), "thyme": (5, 9), "sage": (5, 9), "rosemary": (7, 10),
    "mint": (3, 9), "lemon_balm": (4, 9), "catnip": (3, 9), "lavender": (5, 9),
    "hyssop": (4, 9), "tarragon": (4, 8), "chives": (3, 9), "garlic_chives": (4, 9),
    "sorrel": (4, 9), "white_clover": (3, 10), "avocado": (9.5, 11), "lemon": (9, 11),
    "orange": (9, 11), "olive": (8, 11), "pomegranate": (7.5, 11), "banana": (9.5, 12),
    "mango": (10, 12),
}
LOOSE_SOIL = {"carrot", "parsnip", "potato", "sweet_potato", "peanut", "radish", "daikon",
              "salsify", "horseradish", "celeriac", "garlic", "shallot", "onion_bulb",
              "onion_sets", "leek", "beet", "rutabaga", "turnip", "ginger", "avocado"}
CONTAINER_OK = {"fig", "lemon", "orange", "rosemary", "banana", "lemongrass", "mint",
                "strawberry", "blueberry", "olive", "pomegranate", "avocado", "artichoke"}
for _p in _PLANTS:
    _p["zone"] = ZONES.get(_p["id"])
    _p["soil_pref"] = "loose" if _p["id"] in LOOSE_SOIL else "any"
    _p["container_ok"] = _p["id"] in CONTAINER_OK


def builtin_plants() -> list[dict]:
    return copy.deepcopy(_PLANTS)
