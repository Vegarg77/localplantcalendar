"""Food catalog: the things people eat, mapped to the crop (and variety) that
produces them.

Each entry: food id, display name, plant id (None = not a garden crop),
aliases, typical yield (lb of the eaten product per sq ft of bed per year or
per planting), how it's used ("fresh" = eaten through the season, "store" =
harvested once and kept), a variety tip, optional days-to-maturity for that
variety, and harvest/processing notes.

Yields are rough garden averages (intensive beds, decent care) compiled from
extension "yield per 100 ft of row" tables converted to bed area.
"""

from __future__ import annotations

FOODS: list[dict] = []


def F(fid, name, plant, aliases=(), yld=None, use="fresh", variety=None, dtm=None,
      how=None, unit="lb", default_area=None, note=None):
    FOODS.append({"id": fid, "name": name, "plant_id": plant, "aliases": list(aliases),
                  "yield_lb_sqft": yld, "use": use, "variety": variety, "dtm": dtm,
                  "how": how, "unit": unit, "default_area": default_area, "note": note})


DRY_BEAN_HOW = ("Leave pods on the plants until they are dry, papery and rattle. If rain "
                "is coming, pull whole plants and hang them under cover to finish. "
                "Thresh by stomping the pods in a bag, winnow off chaff, then freeze the "
                "beans 48 hours before storing in jars.")

# ------------------------------------------------------------ beans & pulses
F("pinto_beans", "Pinto beans", "dry_bean", ["pinto", "pintos", "refried beans", "frijoles",
  "frijoles pintos", "charro beans"], 0.07, "store",
  "Bush pinto types such as 'Othello' (~85 days) or 'UI 114' (~90 days)", [85, 92],
  DRY_BEAN_HOW, default_area=32)
F("black_beans", "Black beans", "dry_bean", ["black turtle beans", "frijoles negros",
  "black bean soup"], 0.07, "store", "'Black Turtle' or 'Midnight Black Turtle' (~90–100 days)",
  [90, 100], DRY_BEAN_HOW, default_area=32)
F("kidney_beans", "Kidney beans", "dry_bean", ["red kidney beans", "chili beans",
  "red beans", "red beans and rice"], 0.07, "store",
  "'Dark Red Kidney' or 'Red Kidney' (~95–100 days)", [95, 100], DRY_BEAN_HOW,
  default_area=32)
F("navy_beans", "Navy beans", "dry_bean", ["navy", "white beans", "baked beans", "haricot beans",
  "pea beans"], 0.07, "store", "'Navy' or 'Michelite' (~85–95 days)", [85, 95], DRY_BEAN_HOW,
  default_area=32)
F("great_northern_beans", "Great Northern / cannellini beans", "dry_bean", ["great northern",
  "cannellini", "white kidney beans", "white bean soup"], 0.07, "store",
  "'Great Northern' (~90 days) or 'Cannellini' (~95 days)", [88, 98], DRY_BEAN_HOW,
  default_area=32)
F("cranberry_beans", "Cranberry / borlotti beans", "dry_bean", ["borlotti", "cranberry beans",
  "roman beans"], 0.08, "store", "'Borlotti Lingua di Fuoco' (~65 days fresh, ~85 dry)",
  [80, 90], DRY_BEAN_HOW, default_area=24)
F("green_beans", "Green beans", "bush_bean", ["string beans", "snap beans", "haricots verts",
  "french beans", "green bean casserole"], 0.4, "fresh",
  "Bush types ('Provider' is cold-soil tolerant, 'Contender' is early)", None,
  "Pick every 2–3 days when pods are pencil-thick, before seeds bulge.", default_area=16)
F("pole_beans_food", "Pole beans", "pole_bean", ["runner beans", "climbing beans",
  "kentucky wonder"], 0.5, "fresh", "'Kentucky Wonder' or 'Fortex'", None, None,
  default_area=12)
F("lima_beans", "Lima beans", "lima_bean", ["butter beans", "limas", "succotash"], 0.1,
  "store", "Baby limas ('Henderson', ~65 days) ripen where big limas can't", None,
  "Pick when pods are plump and green for fresh limas, or let them dry for storage.")
F("black_eyed_peas", "Black-eyed peas", "cowpea", ["cowpeas", "southern peas", "field peas",
  "crowder peas", "hoppin john", "purple hull peas"], 0.07, "store",
  "'California Blackeye #5' (~75 days)", None, DRY_BEAN_HOW, default_area=24)
F("chickpeas", "Chickpeas", "chickpea", ["garbanzo", "garbanzo beans", "hummus", "falafel",
  "chana", "chole"], 0.05, "store", "Kabuli types for big tan seeds; desi types are earlier",
  None, "Pull plants when they turn tan and the pods rattle; dry, thresh and store.",
  default_area=32)
F("lentils", "Lentils", "lentil", ["dal", "daal", "lentil soup", "red lentils"], 0.04, "store",
  "'Black Beluga' or French green ('Le Puy') lentils", None,
  "Cut plants when lower pods are brown and rattling; dry in a sheet and thresh.",
  default_area=32)
F("edamame_food", "Edamame", "edamame", ["soybeans", "soy beans", "edamame"], 0.2, "fresh",
  "Short-season types like 'Envy' or 'Midori Giant'", None,
  "Pick when pods are plump but still bright green; boil in salted water.")
F("peanuts", "Peanuts", "peanut", ["peanut butter", "groundnuts", "boiled peanuts"], 0.1,
  "store", "Spanish or Valencia types (~110 days) for shorter seasons", None,
  "Dig when leaves yellow, dry the plants upside down for 2 weeks, then roast.")
F("fava_beans", "Fava beans", "fava", ["broad beans", "favas", "ful medames"], 0.2, "fresh")
F("green_peas", "Green peas", "peas_shell", ["peas", "english peas", "garden peas",
  "shelling peas"], 0.12, "fresh", "'Green Arrow' or 'Lincoln'", None,
  "Pick when pods are round and full; shell and eat or freeze the same day.")
F("snap_peas", "Sugar snap & snow peas", "peas_snap", ["snow peas", "sugar snap peas",
  "snap peas", "mangetout", "stir fry peas"], 0.3, "fresh", "'Sugar Ann' (short) or "
  "'Super Sugar Snap'", None, None)
F("long_beans", "Long beans", "yardlong_bean", ["yardlong beans", "asparagus beans",
  "chinese long beans"], 0.4, "fresh")

# ----------------------------------------------------------------- nightshades
F("tomatoes", "Tomatoes (fresh eating)", "tomato", ["tomato", "slicing tomatoes", "beefsteak",
  "blt", "caprese", "tomato sandwich", "heirloom tomatoes"], 2.0, "fresh",
  "Early/mid slicers: 'Early Girl' (~55 days) for short seasons, 'Better Boy' or "
  "heirlooms like 'Cherokee Purple' where summers are long", None, None, default_area=16)
F("cherry_tomatoes", "Cherry tomatoes", "cherry_tomato", ["grape tomatoes", "sungold"],
  1.5, "fresh", "'Sungold' or 'Sweet Million'", None, None, default_area=8)
F("tomato_sauce", "Tomato sauce & canned tomatoes", "paste_tomato", ["marinara", "pasta sauce",
  "ketchup", "canned tomatoes", "roma tomatoes", "san marzano", "tomato paste", "passata",
  "pizza sauce", "salsa roja"], 2.0, "store", "Determinate paste types ('Roma', 'Amish Paste', "
  "'San Marzano') ripen together for canning", None,
  "Roughly 20 lb of paste tomatoes makes 7 quarts of sauce.", default_area=24)
F("bell_peppers", "Bell peppers", "pepper_sweet", ["peppers", "sweet peppers", "capsicum",
  "stuffed peppers", "fajitas"], 1.0, "fresh", "'Ace' or 'King of the North' for cool "
  "summers; 'California Wonder' where it's hot", None, None, default_area=8)
F("hot_peppers", "Hot peppers", "pepper_hot", ["jalapenos", "jalapeno", "jalapeño",
  "hot peppers", "chiles", "chili peppers", "hot sauce", "serrano", "habanero", "cayenne",
  "chile flakes", "sriracha", "poblano", "anaheim", "hatch chile"], 0.6, "fresh",
  "Jalapeño and serrano are quickest; habanero needs the longest, hottest season", None,
  None, default_area=6)
F("paprika", "Paprika", "pepper_sweet", ["smoked paprika"], 0.1, "store",
  "Thin-walled paprika types ('Alma', 'Hungarian Paprika') dry easily", [75, 85],
  "Let fruit turn fully red, dry, then grind.", default_area=8)
F("eggplant_food", "Eggplant", "eggplant", ["aubergine", "baba ganoush", "eggplant parmesan",
  "ratatouille"], 1.0, "fresh", "Slender Asian types ('Ichiban') set fruit faster in short "
  "seasons", None, None, default_area=8)
F("tomatillos", "Tomatillos", "tomatillo", ["salsa verde", "tomatillo"], 1.0, "fresh",
  None, None, "Harvest when the fruit fills and splits its husk.", default_area=12)
F("potatoes", "Potatoes", "potato", ["potato", "french fries", "fries", "hash browns",
  "mashed potatoes", "potato chips", "baked potato", "potato salad"], 0.8, "store",
  "Early ('Yukon Gold', ~75 days) for new potatoes; mid/late ('Kennebec', 'Russet Burbank') "
  "for storage", None, "For storage, wait until vines die back, then cure the tubers 2 "
  "weeks in a dark, humid spot before storing cool (40°F).", default_area=32)
F("ground_cherries_food", "Ground cherries", "ground_cherry", ["cape gooseberry",
  "husk cherries"], 0.5, "fresh")

# -------------------------------------------------------------------- cucurbits
F("cucumbers", "Cucumbers", "cucumber", ["cucumber", "salad cucumbers", "tzatziki"], 1.0,
  "fresh", "'Marketmore 76' (disease resistant) or 'Diva'", None, None, default_area=8)
F("pickles", "Pickles", "cucumber", ["pickling cucumbers", "dill pickles", "gherkins",
  "bread and butter pickles"], 1.0, "store", "Pickling types like 'Boston Pickling' or "
  "'National Pickling' (~55 days)", [50, 58], "Pick at 3–5 inches every day during the "
  "flush and pickle within a day.", default_area=12)
F("zucchini", "Zucchini & summer squash", "summer_squash", ["summer squash", "courgette",
  "yellow squash", "zucchini bread", "pattypan"], 1.5, "fresh", None, None,
  "Two plants feed a family — pick at 6–8 inches.", default_area=8)
F("winter_squash_food", "Winter squash", "winter_squash", ["butternut squash", "acorn squash",
  "squash soup", "spaghetti squash", "delicata", "kabocha", "hubbard"], 0.6, "store",
  "Butternut stores longest; acorn and delicata ripen soonest", None,
  "Harvest before hard frost, cure 10 days warm, store at 50–55°F for months.",
  default_area=24)
F("pumpkins", "Pumpkins", "pumpkin", ["pumpkin pie", "jack-o-lantern", "pumpkin bread",
  "pie pumpkins"], 0.5, "store", "Sugar pie types for baking", None, None, default_area=32)
F("cantaloupe_food", "Cantaloupe", "cantaloupe", ["muskmelon", "melon", "cantaloupe"], 0.7,
  "fresh", "'Minnesota Midget' or 'Athena' for short seasons", None, None, default_area=16)
F("honeydew_food", "Honeydew", "honeydew", ["honeydew melon", "casaba"], 0.6, "fresh")
F("watermelon_food", "Watermelon", "watermelon", ["watermelons"], 0.8, "fresh",
  "Icebox types ('Sugar Baby', ~75 days) ripen in shorter summers", None, None,
  default_area=24)

# --------------------------------------------------------------------- brassicas
F("broccoli_food", "Broccoli", "broccoli", ["broccoli florets"], 0.4, "fresh",
  "'Green Magic' (heat tolerant) or 'Belstar'", None, None, default_area=12)
F("cabbage_food", "Cabbage", "cabbage", ["coleslaw", "sauerkraut", "slaw", "red cabbage",
  "cabbage rolls"], 1.2, "store", None, None, "About 5 lb of cabbage makes 2 quarts of "
  "sauerkraut.", default_area=12)
F("cauliflower_food", "Cauliflower", "cauliflower", ["cauliflower rice"], 0.5, "fresh")
F("brussels", "Brussels sprouts", "brussels_sprouts", ["brussel sprouts", "sprouts"], 0.3,
  "fresh")
F("kale_food", "Kale", "kale", ["kale chips", "kale salad", "lacinato", "dinosaur kale"],
  0.6, "fresh", None, None, None, default_area=8)
F("collards_food", "Collard greens", "collards", ["collards", "southern greens"], 0.8, "fresh")
F("kohlrabi_food", "Kohlrabi", "kohlrabi", [], 0.5, "fresh")
F("bok_choy_food", "Bok choy", "bok_choy", ["pak choi", "stir fry greens", "baby bok choy"],
  0.6, "fresh")
F("napa_food", "Napa cabbage", "napa_cabbage", ["kimchi", "chinese cabbage", "wombok"], 1.0,
  "store", None, None, "A 10-ft row of napa makes a big batch of kimchi.")
F("radishes", "Radishes", "radish", ["radish"], 0.4, "fresh")
F("daikon_food", "Daikon", "daikon", ["daikon radish", "pickled radish"], 0.8, "store")
F("turnips", "Turnips", "turnip", ["turnip greens"], 0.8, "fresh")
F("rutabagas", "Rutabagas", "rutabaga", ["swede", "neeps"], 1.0, "store")
F("arugula_food", "Arugula", "arugula", ["rocket", "roquette"], 0.25, "fresh")
F("mustard_food", "Mustard greens", "mustard_greens", ["mustard"], 0.4, "fresh")
F("horseradish_food", "Horseradish", "horseradish", ["prepared horseradish", "cocktail sauce"],
  0.3, "store")
F("rapini", "Broccoli rabe", "broccoli_raab", ["rapini", "broccoli raab"], 0.3, "fresh")
F("gai_lan_food", "Chinese broccoli", "gai_lan", ["gai lan", "kai lan"], 0.4, "fresh")

# ----------------------------------------------------------------- leaves & roots
F("salad", "Salad greens", "lettuce_leaf", ["salad", "lettuce", "salad mix", "mesclun",
  "greens", "leaf lettuce", "spring mix"], 0.5, "fresh", "Cut-and-come-again mixes; "
  "heat-tolerant 'Jericho' or 'Muir' for late spring", None,
  "Cut leaves 1 inch above the crown and they regrow 2–3 times.", default_area=12)
F("romaine", "Head lettuce & romaine", "lettuce_head", ["caesar salad", "head lettuce",
  "iceberg", "butterhead", "romaine lettuce"], 0.6, "fresh")
F("spinach_food", "Spinach", "spinach", ["baby spinach", "spanakopita", "saag"], 0.3,
  "fresh", "'Bloomsdale' (cool) or 'Space'", None, None, default_area=12)
F("chard", "Swiss chard", "swiss_chard", ["chard", "rainbow chard", "silverbeet"], 0.8,
  "fresh")
F("endive_food", "Endive & escarole", "endive", ["escarole", "frisee"], 0.5, "fresh")
F("radicchio_food", "Radicchio", "radicchio", [], 0.4, "fresh")
F("celery_food", "Celery", "celery", ["celery sticks", "mirepoix"], 1.5, "fresh")
F("celeriac_food", "Celeriac", "celeriac", ["celery root"], 1.0, "store")
F("beets", "Beets", "beet", ["beet", "beetroot", "borscht", "pickled beets"], 0.8, "store")
F("carrots", "Carrots", "carrot", ["carrot", "carrot cake", "baby carrots"], 1.0, "store",
  "'Napoli' or 'Bolero' (Nantes); 'Danvers' or 'Chantenay' for heavier soil", None,
  "Fall carrots can stay in the ground under mulch and be dug as needed.", default_area=16)
F("parsnips", "Parsnips", "parsnip", ["parsnip"], 0.8, "store")
F("onions", "Onions", "onion_bulb", ["onion", "yellow onions", "red onions", "sweet onions",
  "white onions", "caramelized onions", "french onion soup"], 1.0, "store",
  "Match day length to your latitude: long-day north of ~37°N, intermediate 32–38°N, "
  "short-day farther south", None, "Harvest when half the tops flop; cure 2–3 weeks in "
  "shade before storing.", default_area=16)
F("garlic_food", "Garlic", "garlic", ["garlic", "garlic bread", "roasted garlic", "aioli"],
  0.4, "store", "Hardneck ('Music', 'German Extra Hardy') where winters are cold; softneck "
  "('Inchelium Red') in mild climates", None, "Save your biggest heads to replant each fall.",
  default_area=16)
F("leeks", "Leeks", "leek", ["leek", "potato leek soup"], 0.8, "fresh")
F("shallots", "Shallots", "shallot", ["shallot"], 0.5, "store")
F("green_onions", "Green onions", "scallion", ["scallions", "spring onions", "green onion"],
  0.4, "fresh")
F("chives_food", "Chives", "chives", ["chive"], 0.2, "fresh")
F("sweet_corn_food", "Sweet corn", "sweet_corn", ["corn on the cob", "corn", "fresh corn",
  "elote"], 0.3, "fresh", "Sugary-enhanced (se) types tolerate cooler soil than supersweets",
  None, "Pick when silks are brown and a kernel squirts milky juice.", default_area=40)
F("popcorn_food", "Popcorn", "popcorn", ["popcorn"], 0.15, "store",
  "'Robust' or 'Tom Thumb' (short season)", [85, 100],
  "Let ears dry on the stalk, then cure indoors until kernels pop well.", default_area=40)
F("cornmeal", "Cornmeal & tortillas", "popcorn", ["corn tortillas", "tortillas", "polenta",
  "grits", "masa", "cornbread", "hominy", "flour corn", "dent corn"], 0.15, "store",
  "Flour/dent corn: 'Painted Mountain' (~90 days, very short season), 'Bloody Butcher' or "
  "'Hopi Blue' where summers are long", [90, 110],
  "Dry ears on the stalk, shell and grind; nixtamalize with lime for masa.",
  default_area=48)
F("okra_food", "Okra", "okra", ["gumbo", "fried okra"], 0.4, "fresh",
  "'Clemson Spineless'; 'Cajun Delight' is faster for northern gardens", None, None)
F("sweet_potatoes", "Sweet potatoes", "sweet_potato", ["yams", "sweet potato fries",
  "sweet potato pie"], 0.8, "store", "'Georgia Jet' or 'Beauregard' (~90–100 days) for "
  "shorter seasons", None, "Dig before soil cools below 55°F; cure 10 days warm and humid, "
  "then they sweeten in storage.", default_area=24)
F("ginger_food", "Ginger", "ginger", ["fresh ginger", "baby ginger"], 0.5, "store")
F("sunflower_seeds", "Sunflower seeds", "sunflower", ["sunflower seeds"], 0.05, "store",
  "'Mammoth Grey Stripe' for eating seeds", None,
  "Cut heads when the backs turn yellow-brown; hang to dry with a bag over them.")
F("amaranth_food", "Amaranth", "amaranth", ["callaloo", "amaranth greens"], 0.4, "fresh")
F("asparagus_food", "Asparagus", "asparagus", [], 0.15, "fresh", None, None,
  "Snap spears at the soil when 7–9 inches tall; stop when spears get thin.", default_area=40)
F("rhubarb_food", "Rhubarb", "rhubarb", ["rhubarb pie", "strawberry rhubarb"], 0.6, "fresh",
  default_area=9)
F("artichokes", "Artichokes", "artichoke", ["artichoke"], 0.3, "fresh")
F("sunchokes", "Sunchokes", "jerusalem_artichoke", ["jerusalem artichokes"], 1.0, "store")
F("fennel", "Fennel", "fennel_bulb", ["fennel bulb", "finocchio"], 0.6, "fresh")

# ------------------------------------------------------------------------- herbs
F("basil_food", "Basil", "basil", ["pesto", "thai basil", "sweet basil"], 0.3, "fresh",
  "'Genovese' for pesto; 'Prospera' resists downy mildew", None,
  "Pinch tops weekly; one plant gives ~1 cup of leaves a week in summer.", default_area=6)
F("cilantro_food", "Cilantro", "cilantro", ["coriander", "coriander leaf"], 0.15, "fresh",
  "Slow-bolt types ('Calypso', 'Santo')", None, None, default_area=4)
F("parsley_food", "Parsley", "parsley", ["tabbouleh", "flat leaf parsley", "chimichurri"],
  0.4, "fresh", default_area=4)
F("dill_food", "Dill", "dill", ["dill weed", "dill seed"], 0.15, "fresh", default_area=4)
F("mint_food", "Mint", "mint", ["mojito", "mint tea", "peppermint", "spearmint"], 0.4,
  "fresh", default_area=4)
F("oregano_food", "Oregano", "oregano", [], 0.2, "fresh", default_area=4)
F("thyme_food", "Thyme", "thyme", [], 0.1, "fresh", default_area=2)
F("sage_food", "Sage", "sage", [], 0.2, "fresh", default_area=4)
F("rosemary_food", "Rosemary", "rosemary", [], 0.2, "fresh", default_area=4)
F("chamomile_tea", "Chamomile tea", "chamomile", ["chamomile"], 0.05, "store",
  default_area=4)
F("lemongrass_food", "Lemongrass", "lemongrass", [], 0.3, "fresh", default_area=4)
F("lavender_food", "Lavender", "lavender", [], 0.05, "store", default_area=4)

# ------------------------------------------------------------------------- fruit
F("strawberries", "Strawberries", "strawberry", ["strawberry", "strawberry jam",
  "strawberry shortcake"], 0.5, "fresh", "June-bearing for jam batches, day-neutral "
  "('Albion', 'Seascape') for berries all summer", None, None, default_area=24)
F("raspberries", "Raspberries", "raspberry", ["raspberry", "raspberry jam"], 0.4, "fresh",
  default_area=24)
F("blackberries", "Blackberries", "blackberry", ["blackberry", "cobbler"], 0.5, "fresh",
  default_area=24)
F("blueberries", "Blueberries", "blueberry", ["blueberry", "blueberry muffins"], 0.25,
  "fresh", "Northern highbush in the North; rabbiteye or southern highbush in the South",
  None, None, default_area=25)
F("grapes", "Grapes", "grape", ["grape", "raisins", "grape juice", "wine", "grape jelly"],
  0.5, "fresh", default_area=64)
F("apples", "Apples", "apple", ["apple", "apple pie", "cider", "applesauce"], 1.0, "store",
  "Choose by chill hours and disease resistance ('Liberty', 'Enterprise')", None, None,
  default_area=100)
F("pears", "Pears", "pear", ["pear"], 0.8, "store", default_area=100)
F("peaches", "Peaches", "peach", ["peach", "nectarines", "peach cobbler"], 0.8, "fresh",
  default_area=100)
F("cherries", "Cherries", "cherry", ["cherry", "cherry pie", "sour cherries"], 0.6, "fresh",
  default_area=100)
F("plums", "Plums", "plum", ["plum", "prunes"], 0.6, "fresh", default_area=100)
F("figs", "Figs", "fig", ["fig", "fig jam"], 0.5, "fresh", default_area=64)
F("avocados", "Avocados", "avocado", ["avocado", "guacamole", "avocado toast"], 0.5, "fresh",
  default_area=200)
F("lemons", "Lemons & limes", "lemon", ["lemon", "lemonade", "limes", "lime", "key lime pie",
  "meyer lemon"], 0.6, "fresh", "Meyer lemon is the most cold-tolerant and pot-friendly",
  None, None, default_area=64)
F("oranges", "Oranges", "orange", ["orange", "orange juice", "mandarins", "tangerines",
  "clementines", "satsumas"], 0.8, "fresh", default_area=100)
F("olives", "Olives", "olive", ["olive", "olive oil"], 0.3, "store", default_area=200)
F("pomegranates", "Pomegranates", "pomegranate", ["pomegranate"], 0.5, "fresh",
  default_area=100)
F("bananas", "Bananas", "banana", ["banana", "plantains"], 0.5, "fresh", default_area=100)
F("mangoes", "Mangoes", "mango", ["mango"], 0.5, "fresh", default_area=200)

# ------------------------------------------------- foods that aren't garden crops
F("coffee", "Coffee", None, ["coffee beans", "espresso"], note=(
    "Coffee is a tropical shrub that needs frost-free, humid conditions (zone 10b+). It can "
    "live as a houseplant but rarely yields enough to brew."))
F("chocolate", "Chocolate / cacao", None, ["cacao", "cocoa"], note=(
    "Cacao only grows in hot, humid rainforest climates within ~20° of the equator."))
F("vanilla", "Vanilla", None, [], note=(
    "Vanilla is a tropical orchid that needs hand pollination and a heated greenhouse."))
F("black_pepper", "Black pepper", None, ["peppercorns"], note=(
    "Black pepper is a tropical vine (Piper nigrum) — not a garden crop outside the tropics. "
    "For heat from your garden, grow hot peppers."))
F("cinnamon", "Cinnamon", None, [], note="Cinnamon is the bark of a tropical tree.")
F("coconut", "Coconut", None, ["coconut milk"], note=(
    "Coconut palms need tropical, frost-free coasts (zone 11+)."))
F("rice", "Rice", None, ["brown rice", "white rice"], note=(
    "Rice needs a long hot season and flooded paddies; home yields are ~0.3 lb per sq ft at "
    "best. This planner doesn't schedule grains yet."))
F("wheat", "Wheat / flour", None, ["flour", "bread", "pasta", "whole wheat"], note=(
    "Wheat grows almost anywhere, but a 1,000 sq ft patch yields only ~50–100 lb of grain "
    "and needs threshing and milling. This planner doesn't schedule grains yet."))
F("pineapple", "Pineapple", None, [], note=(
    "Pineapple needs frost-free warmth (zone 11) or a sunny windowsill, and takes ~2 years "
    "to fruit from a top."))

# --------------------------------------------------------------- dish bundles
BUNDLES = {
    "salsa": {"name": "Salsa", "foods": ["tomato_sauce", "hot_peppers", "onions",
                                         "cilantro_food", "tomatillos"]},
    "pesto": {"name": "Pesto", "foods": ["basil_food", "garlic_food"]},
    "three_sisters": {"name": "Three Sisters (corn, beans, squash)",
                      "foods": ["cornmeal", "pinto_beans", "winter_squash_food"]},
    "salad": {"name": "Salad all season", "foods": ["salad", "spinach_food", "radishes",
                                                    "cucumbers", "cherry_tomatoes"]},
    "stir_fry": {"name": "Stir-fry", "foods": ["bok_choy_food", "snap_peas", "broccoli_food",
                                               "green_onions", "garlic_food"]},
    "pizza": {"name": "Pizza garden", "foods": ["tomato_sauce", "bell_peppers", "onions",
                                                "basil_food", "oregano_food"]},
    "pickles": {"name": "Pickles", "foods": ["pickles", "dill_food", "garlic_food"]},
    "chili": {"name": "Chili", "foods": ["kidney_beans", "tomato_sauce", "onions",
                                         "hot_peppers", "bell_peppers"]},
    "soup": {"name": "Soup pot", "foods": ["onions", "carrots", "celery_food", "potatoes",
                                           "garlic_food", "parsley_food"]},
    "tacos": {"name": "Taco night", "foods": ["cornmeal", "black_beans", "tomatoes",
                                              "hot_peppers", "cilantro_food", "onions"]},
}
