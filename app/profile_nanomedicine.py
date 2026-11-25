"""Domain knowledge for the nanomedicine dataset.

Applies only when the uploaded CSV has `drug_name` and `api_norm` columns.
Class and platform mappings reflect the known properties of each product.
The raw CSV is never modified; these are extra columns derived during analysis.
"""
import re

REQUIRED = {"drug_name", "api_norm"}

# product: (drug class, platform, match terms)
PRODUCTS = {
    "Doxil": ("Anthracycline", "Liposome", "doxil|caelyx|doxorubicin|pld|dox\\b|adriamycin"),
    "Myocet": ("Anthracycline", "Liposome", "myocet|doxorubicin|dox\\b|adriamycin"),
    "DaunoXome": ("Anthracycline", "Liposome", "daunoxome|daunorubicin|dnr"),
    "MM-302": ("Anthracycline", "Liposome", "mm-?302|doxorubicin"),
    "ThermoDox": ("Anthracycline", "Liposome", "thermodox|doxorubicin|ltsl"),
    "Abraxane": ("Taxane", "Albumin nanoparticle", "abraxane|paclitaxel|nab-"),
    "Genexol-PM": ("Taxane", "Micelle", "genexol|paclitaxel"),
    "Apealea": ("Taxane", "Micelle", "apealea|paclitaxel|paclical"),
    "Lipusu": ("Taxane", "Liposome", "lipusu|paclitaxel"),
    "Liporaxel": ("Taxane", "Lipid-based (other)", "liporaxel|paclitaxel|dhp107"),
    "NK105": ("Taxane", "Micelle", "nk-?105|paclitaxel"),
    "EndoTAG-1": ("Taxane", "Liposome", "endotag|paclitaxel"),
    "Nanoxel": ("Taxane", "Micelle", "nanoxel|docetaxel|paclitaxel"),
    "Nanoxel-M": ("Taxane", "Micelle", "nanoxel|docetaxel"),
    "BIND-014": ("Taxane", "Polymeric nanoparticle", "bind-?014|docetaxel"),
    "CriPEC": ("Taxane", "Micelle", "cripec|docetaxel"),
    "PNU166945": ("Taxane", "Polymer conjugate", "pnu-?166945|paclitaxel"),
    "NKTR-105": ("Taxane", "Polymer conjugate", "nktr-?105|docetaxel"),
    "SPI-077": ("Platinum", "Liposome", "spi-?077|cisplatin"),
    "NC-6004": ("Platinum", "Micelle", "nc-?6004|cisplatin"),
    "NC-4016": ("Platinum", "Micelle", "nc-?4016|oxaliplatin|dach"),
    "ProLindac": ("Platinum", "Polymer conjugate", "prolindac|ap-?5346|dach|oxaliplatin"),
    "AP5280": ("Platinum", "Polymer conjugate", "ap-?5280|platin"),
    "Marqibo": ("Vinca alkaloid", "Liposome", "marqibo|vincristine|vcr"),
    "Onivyde": ("Topoisomerase I inhibitor", "Liposome", "onivyde|irinotecan|mm-?398|nal-?iri"),
    "DepoCyt": ("Antimetabolite", "Liposome", "depocyt|cytarabine|ara-?c"),
    "Vyxeos": ("Antimetabolite + anthracycline", "Liposome", "vyxeos|cpx-?351|cytarabine|daunorubicin"),
    "Oncaspar": ("Enzyme", "Polymer conjugate", "oncaspar|asparaginase|peg-?asp|pegaspargase"),
    "CALAA-01 siRNA": ("siRNA", "Polymeric nanoparticle", "calaa"),
    "Mepact": ("Immunomodulator", "Liposome", "mepact|mifamurtide|mtp"),
    "Fyarro": ("mTOR inhibitor", "Albumin nanoparticle", "fyarro|sirolimus|rapamycin|abi-?009"),
    "AGuIX": ("Inorganic / physical action", "Inorganic", "aguix|gadolinium"),
    "Hensify": ("Inorganic / physical action", "Inorganic", "hensify|nbtxr3|hafnium"),
    "Feraheme": ("Inorganic / physical action", "Inorganic", "feraheme|ferumoxytol"),
    "Nanotherm": ("Inorganic / physical action", "Inorganic", "nanotherm|iron oxide"),
    "AuroShell": ("Inorganic / physical action", "Inorganic", "auroshell|gold|nanoshell"),
}

GROUPS = {
    "Identity and active ingredient": ["drug_name", "pdf", "active_pharmaceutical_ingredient", "api_norm", "payload",
        "anthracycline_drug_class", "antimetabolite_drug_class", "nucleoside_analogue_drug_class", "platin_drug_class",
        "taxane_drug_class", "topoisomerase_drug_class", "topoisomerase_i_inhibitor_drug_class"],
    "Formulation": ["nanoparticle_type", "np_type_norm", "nanoparticle_formulation", "nanoparticle_composition",
        "liposome_formulation", "lipid_nanoparticle_formulation", "micelle_formulation", "polymer_material",
        "metal_nanoparticle_material", "excipient", "surface_material", "pegylation", "polyethylene_glycol", "stealth_property"],
    "Physicochemistry": ["particle_size", "particle_size_clean", "particle_diameter", "hydrodynamic_diameter", "hydrodynamic_radius",
        "polydispersity", "dispersity", "zeta_potential", "particle_charge", "particle_internal_charge", "particle_shape",
        "aggregation", "colloidal_stability", "nanoparticle_stability", "critical_micelle_concentration",
        "encapsulation_efficiency", "loading_capacity", "protein_corona"],
    "Pharmacokinetics and distribution": ["auc_pk_parameter", "cmax_pk_parameter", "half_life", "terminal_half_life", "clearance_rate",
        "volume_of_distribution", "blood_circulation", "drug_retention", "injected_dose", "percent_injected_dose",
        "percent_injected_dose_per_g", "organ_uptake", "tissue_uptake"],
    "Preclinical": ["cell_line", "cell_uptake", "cytotoxicity", "ic50_inhibitory_concentration", "ld50_lethal_dose", "body_weight"],
    "Dosing and administration": ["dose_mg_per_kg", "dose_mg_per_kg_clean", "dose_mg_per_m2", "maximum_tolerated_dose", "treatment_schedule",
        "inhalation_administration", "insufflation_administration", "intramuscular_administration", "intranasal_administration",
        "intraperitoneal_administration", "intrathecal_administration", "intratumoral_administration",
        "intravenous_administration", "oral_administration", "parenteral_administration", "subcutaneous_administration"],
    "Disease": ["disease_any", "carcinoma_disease", "leukemia_disease", "melanoma_disease", "sarcoma_disease", "metastatic_disease",
        "intracranial_disease", "advanced_disease_status", "disease_stage", "disease_stage_grade", "resectable_disease_status"],
    "Clinical study": ["clinical_trial_number", "clinical_trial_stage", "clinical_trial_type", "phase_norm", "phase_i_trial",
        "phase_ii_trial", "phase_iii_trial", "phase_iv_trial", "blind_study_design", "double_blind_study_design",
        "open_label_study_design", "randomized_controlled_trial", "retrospective_study_design", "longitudinal_study_design",
        "first_in_man_study", "dose_escalation_study", "number_of_patients", "number_of_patients_clean",
        "intention_to_treat_population", "drop_out", "clinical_follow_up_period"],
    "Treatment context": ["chemotherapy_treatment", "combination_therapy", "immunotherapy", "monotherapy", "radiotherapy",
        "pre_treatment", "first_line_treatment"],
    "Efficacy": ["overall_survival", "progression_free_survival", "disease_free_survival", "overall_response_rate",
        "partial_response", "pathological_complete_response", "durability_of_response"],
    "Safety": ["adverse_reactions", "cardiotoxicity", "hepatotoxicity", "nephrotoxicity", "neurotoxicity", "neutropenia",
        "anemia", "toxicity_grade", "tolerability"],
}

# Charts use the cleaned column instead of the raw one.
PREFERRED = {"particle_size": "particle_size_clean", "dose_mg_per_kg": "dose_mg_per_kg_clean",
             "number_of_patients": "number_of_patients_clean"}

# Column: (lower bound, upper bound, unit). Values outside are excluded from distributions and counted under data quality.
VALID = {
    "particle_size_clean": (1, 5000, "nm"), "particle_size": (1, 5000, "nm"), "particle_diameter": (1, 5000, "nm"),
    "hydrodynamic_diameter": (1, 5000, "nm"), "hydrodynamic_radius": (0.5, 2500, "nm"),
    "zeta_potential": (-100, 100, "mV"), "polydispersity": (0, 1, "PDI"),
    "dose_mg_per_kg_clean": (0.0001, 1000, "mg/kg"), "dose_mg_per_kg": (0.0001, 1000, "mg/kg"),
    "dose_mg_per_m2": (0.01, 5000, "mg/m²"), "number_of_patients_clean": (1, 100000, "patients"),
    "number_of_patients": (1, 100000, "patients"), "half_life": (0.0001, None, None), "terminal_half_life": (0.0001, None, None),
    "clearance_rate": (0, None, None), "injected_dose": (0, None, None), "body_weight": (0, None, None),
    "ic50_inhibitory_concentration": (0, None, None), "loading_capacity": (0, None, None), "clinical_follow_up_period": (0, None, None),
}

MIXED_UNITS = {"half_life", "terminal_half_life", "clearance_rate", "injected_dose", "body_weight",
               "ic50_inhibitory_concentration", "loading_capacity", "clinical_follow_up_period",
               "auc_pk_parameter", "cmax_pk_parameter", "volume_of_distribution", "maximum_tolerated_dose"}

LABELS = {
    "drug_name": "Product", "pdf": "Source file", "active_pharmaceutical_ingredient": "Active ingredient (raw)", "api_norm": "Active ingredient",
    "payload": "Payload", "nanoparticle_type": "Nanoparticle type (raw)", "np_type_norm": "Nanoparticle type", "particle_size": "Particle size (raw)",
    "particle_size_clean": "Particle size", "polydispersity": "Polydispersity index", "zeta_potential": "Zeta potential",
    "auc_pk_parameter": "AUC", "cmax_pk_parameter": "Cmax", "percent_injected_dose": "Percent injected dose (%ID)", "percent_injected_dose_per_g": "%ID per gram",
    "ic50_inhibitory_concentration": "IC50", "ld50_lethal_dose": "LD50", "dose_mg_per_kg": "Dose per kg (raw)", "dose_mg_per_kg_clean": "Dose per body weight",
    "dose_mg_per_m2": "Dose per body surface area", "disease_any": "Disease", "phase_norm": "Clinical phase", "phase_i_trial": "Phase I mentions",
    "phase_ii_trial": "Phase II mentions", "phase_iii_trial": "Phase III mentions", "phase_iv_trial": "Phase IV mentions",
    "number_of_patients": "Number of patients (raw)", "number_of_patients_clean": "Number of patients", "clinical_follow_up_period": "Follow-up period",
    "drop_out": "Drop-out", "first_in_man_study": "First-in-human study", "topoisomerase_i_inhibitor_drug_class": "Topoisomerase I inhibitor mentions",
    "anthracycline_drug_class": "Anthracycline mentions", "antimetabolite_drug_class": "Antimetabolite mentions", "nucleoside_analogue_drug_class": "Nucleoside analogue mentions",
    "platin_drug_class": "Platinum mentions", "taxane_drug_class": "Taxane mentions", "topoisomerase_drug_class": "Topoisomerase mentions",
    "chemotherapy_treatment": "Chemotherapy", "first_line_treatment": "First-line treatment", "pre_treatment": "Pre-treatment",
    "resectable_disease_status": "Resectability", "disease_stage_grade": "Disease stage or grade", "advanced_disease_status": "Advanced disease status",
}
_SHORT = re.compile(r"_(administration|disease|study_design|formulation)$")

def label(c):
    if c in LABELS: return LABELS[c]
    m = _SHORT.search(c)
    if c.endswith("_administration"): return c[: -len("_administration")].replace("_", " ").capitalize() + " route"
    return c.replace("_", " ").capitalize()

PHASE_MAP = {"Faz I": "Phase I", "Faz II": "Phase II", "Faz III": "Phase III", "Faz IV": "Phase IV"}
NP_MAP = {"Lipozom": "Liposome", "Misel": "Micelle", "Diğer": "Other", "Nanoparçacık (genel)": "Nanoparticle (general)",
          "Albumin nanoparçacık": "Albumin nanoparticle", "Polimerik nanoparçacık": "Polymeric nanoparticle", "LNP": "LNP"}

# Raw columns that duplicate a cleaned one; left out where duplicates would mislead.
RAW_DUPES = {"active_pharmaceutical_ingredient", "nanoparticle_type", "particle_size", "dose_mg_per_kg", "number_of_patients"}

def localize(df):
    """The CSV stores two normalized columns in Turkish; show them in English (in memory only)."""
    if "phase_norm" in df: df["phase_norm"] = df["phase_norm"].replace(PHASE_MAP)
    if "np_type_norm" in df: df["np_type_norm"] = df["np_type_norm"].replace(NP_MAP)

DISEASE_RULES = [
    ("Breast", r"breast|tnbc|her2"),
    ("Ovarian and gynecologic", r"ovar|cervic|endometr|uterine"),
    ("Lung", r"lung|nsclc|sclc|mesothelioma"),
    ("Pancreatic", r"pancrea|pdac"),
    ("Gastrointestinal and liver", r"colo|gastric|stomach|esophag|oesophag|hepat|hcc|liver|biliary|cholangio|\bcrc\b"),
    ("Hematologic", r"leuk|lymphom|myelom|\baml\b|\ball\b|\bcll\b|\bcml\b|hodgkin|mds|myelodys"),
    ("Melanoma and skin", r"melanom|skin|kaposi"),
    ("Sarcoma", r"sarcom|osteosarc"),
    ("Brain and nervous system", r"glio|brain|neuroblast|meningeal|cns\b|intracran"),
    ("Head and neck", r"head and neck|hnscc|nasophar|oral cancer"),
    ("Urogenital", r"prostat|bladder|renal|kidney|urothel"),
    ("General tumor or metastasis", r"metasta|tumou?r|carcinom|cancer|malign|neoplas|adenocarc"),
]
_compiled = [(n, re.compile(p, re.I)) for n, p in DISEASE_RULES]

def disease_group(v):
    if not isinstance(v, str):
        return "Not specified"
    for n, p in _compiled:
        if p.search(v):
            return n
    return "Other"

SAMPLE_COLUMNS = ["drug_name", "api_norm", "phase_norm", "disease_any", "particle_size_clean", "zeta_potential",
                  "polydispersity", "dose_mg_per_kg_clean", "dose_mg_per_m2", "number_of_patients_clean",
                  "half_life", "cell_line", "adverse_reactions", "overall_survival"]

CLUSTER_BASES = {
    "terms_all": {"label": "All terms", "desc": "Every phrase found in the records", "kind": "terms", "groups": None},
    "info_type": {"label": "Information type", "desc": "Which fields are filled, regardless of content", "kind": "presence", "groups": None},
    "terms_form": {"label": "Formulation and physicochemistry", "desc": "Carrier, surface and stability phrases", "kind": "terms", "groups": ["Formulation", "Physicochemistry"]},
    "terms_clin": {"label": "Clinical and disease", "desc": "Study design, disease and treatment context", "kind": "terms", "groups": ["Clinical study", "Disease", "Treatment context"]},
    "terms_safe": {"label": "Efficacy and safety", "desc": "Survival, response and toxicity phrases", "kind": "terms", "groups": ["Efficacy", "Safety"]},
}

def derive(df):
    """Adds analysis columns without touching the raw CSV."""
    out = {}
    out["_class"] = df["drug_name"].map(lambda d: PRODUCTS.get(d, ("Unclassified",))[0])
    out["_platform"] = df["drug_name"].map(lambda d: PRODUCTS.get(d, (None, "Unclassified"))[1])
    out["_phase"] = df["phase_norm"].fillna("Not specified") if "phase_norm" in df else "Not specified"
    out["_disease"] = df["disease_any"].map(disease_group) if "disease_any" in df else "Not specified"
    return out

DIMS = [("_product", "Product"), ("_class", "Drug class"), ("_platform", "Platform"), ("_phase", "Clinical phase"), ("_disease", "Disease group")]
PHASE_ORDER = ["Phase I", "Phase II", "Phase III", "Phase IV", "Not specified"]
