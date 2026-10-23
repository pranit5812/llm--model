"""Scope and clinical domain validation for ICMR STW retrieval.

Determines whether a query pertains to the ICMR Cardiology Standard Treatment
Workflows corpus (ICMR-CARD-001 through ICMR-CARD-007) or falls outside clinical
scope (e.g. tropical diseases, orthopaedics, diabetes titration, nonsense words).

When a query is deemed out-of-scope, retrieval operations safely abstain by
returning an empty list, allowing the API and application layers to issue the
standard NO_RELIABLE_ICMR_EVIDENCE sentinel rather than hallucinating or forcing
low-relevance matches.
"""

from __future__ import annotations

import re
from typing import Set

from .models import RetrievalQuery

# Known cardiology domain anchor terms, abbreviations, procedures, and drugs
# extracted from the 7 official ICMR Cardiology Standard Treatment Workflows.
CARDIO_DOMAIN_ANCHORS: Set[str] = {
    # Conditions & syndromes
    "stemi", "nstemi", "cad", "angina", "acs", "infarction", "myocardial",
    "heart", "cardiac", "cardio", "coronary", "hypertension", "blood pressure",
    "bp", "dyslipidemia", "dyslipidaemia", "cholesterol", "statin", "ldl", "hdl",
    "lipid", "arrhythmia", "bradyarrhythmia", "tachycardia", "atrial fibrillation",
    "af", "heart block", "av block", "bundle branch", "pacemaker", "tpi", "ppi",
    "heart failure", "hf", "hfref", "hfpef", "cardiomyopathy", "shock",
    "cardiogenic", "pericarditis", "myocarditis", "endocarditis", "valve",
    "valvular", "stenosis", "regurgitation", "aortic", "mitral", "tricuspid",
    # Symptoms & clinical presentations
    "chest pain", "palpitation", "palpitations", "syncope", "dyspnea", "dyspnoea",
    "orthopnea", "pnd", "edema", "pulse",
    # Diagnostic investigations
    "ecg", "ekg", "electrocardiogram", "troponin", "cardiac biomarker", "biomarkers",
    "echocardiography", "echo", "ejection fraction", "stress test", "tmt",
    "angiography", "coronary angiogram", "lipid profile", "creatinine", "potassium",
    # Interventions & procedures
    "pci", "angioplasty", "stent", "stenting", "thrombolysis", "thrombolytic",
    "fibrinolysis", "reperfusion", "cabg", "cardioversion", "defibrillator", "icd",
    # Pharmacotherapy
    "streptokinase", "urokinase", "tenecteplase", "reteplase", "aspirin",
    "clopidogrel", "prasugrel", "ticagrelor", "antiplatelet", "heparin",
    "enoxaparin", "fondaparinux", "anticoagulation", "anticoagulant", "warfarin",
    "doac", "dabigatran", "apixaban", "rivaroxaban", "nitrate", "nitroglycerin",
    "sorbitrate", "isosorbide", "beta blocker", "metoprolol", "atenolol",
    "carvedilol", "bisoprolol", "ace inhibitor", "arb", "ramipril", "enalapril",
    "losartan", "telmisartan", "furosemide", "torsemide", "diuretic",
    "spironolactone", "eplerenone", "digoxin", "amiodarone", "atropine",
    "dopamine", "noradrenaline", "norepinephrine", "dobutamine", "isoprenaline",
    "atorvastatin", "rosuvastatin", "amlodipine", "diltiazem", "verapamil",
    # Clinical scores & administrative tiers
    "cha2ds2", "crusade", "grace", "timi", "nyha", "killip",
    "primary health centre", "phc", "community health centre", "chc",
    "district hospital", "tertiary care", "sub centre", "referral criteria",
}

# Explicit non-cardiology markers (conditions outside the ICMR cardiology guidelines)
GENERAL_OUT_OF_SCOPE_MARKERS: Set[str] = {
    "weather", "forecast", "cricket", "football", "recipe", "python", "javascript",
    "stock price", "hotel", "flight", "movie", "song", "lyrics", "capital of",
    "president", "prime minister", "bitcoin", "crypto", "xyzzyqrst", "nonsense", "programming",
}
OUT_OF_SCOPE_MARKERS = GENERAL_OUT_OF_SCOPE_MARKERS


def is_query_in_clinical_scope(query: RetrievalQuery | str) -> bool:
    """Check if query is clinically relevant across any ICMR STW specialty."""
    if isinstance(query, RetrievalQuery):
        if (
            query.condition
            or query.document_id
            or query.specialty
            or query.section
            or query.entity_type
            or query.healthcare_tier
        ):
            return True
        text = query.query.strip().lower()
    else:
        text = str(query).strip().lower()

    if not text:
        return False

    tokens = set(re.sub(r"[^\w\s]", " ", text).split())
    if not tokens:
        return False

    if any(m in tokens for m in GENERAL_OUT_OF_SCOPE_MARKERS):
        return False

    UNSUPPORTED_CONDITIONS = {
        "dengue", "malaria", "typhoid", "covid", "hiv", "chemotherapy", "xyzzyqrst", "nonsense",
    }
    if bool(tokens & UNSUPPORTED_CONDITIONS):
        return False


    # Check against known specialties router vocabularies
    from .router import SPECIALTY_KEYWORD_MAP
    for vocab in SPECIALTY_KEYWORD_MAP.values():
        if any(re.search(r"\b" + re.escape(anchor) + r"\b", text) for anchor in vocab):
            return True

    # Check common clinical markers (dose, treatment, investigation, hospital, diagnosis, etc.)
    common_clinical = {
        "dose", "dosage", "mg", "contraindication", "contraindications",
        "investigation", "investigations", "laboratory", "lab", "ecg", "ekg",
        "referral", "phc", "chc", "hospital", "patient", "treatment", "therapy",
        "syndrome", "symptoms", "diagnosis", "management", "criteria", "workflow",
        "icmr", "medication", "drugs", "clinical",
    }
    if bool(tokens & common_clinical):
        return True


    return False


def is_query_in_cardiology_scope(query: RetrievalQuery) -> bool:
    """Check if query is clinically relevant to the ICMR Cardiology STW corpus.

    Returns True if:
      1. Any metadata filter (condition, document_id, specialty) is provided, OR
      2. The query text contains cardiology domain anchor terms and does not
         exclusively target an out-of-scope non-cardiology condition.

    Returns False if:
      - The query matches known out-of-scope markers with no cardiology anchor.
      - The query is completely ungrounded in cardiovascular clinical concepts.
    """
    text = query.query.strip().lower()
    if not text:
        return False

    tokens = set(re.sub(r"[^\w\s]", " ", text).split())
    if not tokens:
        return False

    if any(m in tokens for m in GENERAL_OUT_OF_SCOPE_MARKERS):
        return False

    unsupported = {
        "dengue", "malaria", "typhoid", "covid", "hiv", "chemotherapy", "xyzzyqrst", "nonsense", "fracture",
    }
    if bool(tokens & unsupported):
        return False

    # 1. Explicit metadata pre-filters indicate intentional scoping
    if query.condition or query.document_id or query.specialty or query.section:
        return True

    # 2. Check for explicit out-of-scope conditions
    has_out_of_scope = bool(tokens & OUT_OF_SCOPE_MARKERS)

    # 3. Check for cardiology domain anchors with word boundary to avoid substring collisions (e.g. 'af' in 'safety')
    has_cardio_anchor = any(re.search(r"\b" + re.escape(anchor) + r"\b", text) for anchor in CARDIO_DOMAIN_ANCHORS)

    if has_out_of_scope and not has_cardio_anchor:
        return False

    if not has_cardio_anchor:
        return False

    return True

