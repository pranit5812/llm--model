"""Specialty Query Router for the ICMR Standard Treatment Workflow Platform.

Provides lightweight deterministic routing from natural-language clinical queries
to candidate ICMR specialties, without overriding retrieval evidence.

If routing confidence is low or ambiguous, the router falls back to searching
the broader approved corpus.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

SPECIALTY_KEYWORD_MAP: Dict[str, Set[str]] = {
    "Cardiology": {
        "stemi", "nstemi", "cad", "angina", "acs", "infarction", "myocardial",
        "heart", "cardiac", "cardio", "coronary", "hypertension", "blood pressure",
        "bp", "dyslipidemia", "dyslipidaemia", "cholesterol", "statin", "ldl", "hdl",
        "lipid", "arrhythmia", "bradyarrhythmia", "tachycardia", "atrial fibrillation",
        "af", "heart block", "av block", "bundle branch", "pacemaker", "tpi", "ppi",
        "heart failure", "hf", "hfref", "hfpef", "cardiomyopathy", "cardiogenic shock",
        "cardiogenic", "pericarditis", "myocarditis", "endocarditis", "valve",
        "valvular", "troponin", "pci", "angioplasty", "thrombolysis", "streptokinase",
        "tenecteplase", "aspirin", "clopidogrel", "atorvastatin", "heparin", "chest pain",
    },
    "Neurology": {
        "stroke", "paralysis", "acute paralysis", "hemiplegia", "paraplegia",
        "dementia", "alzheimer", "cognitive impairment", "epilepsy", "seizure",
        "convulsion", "status epilepticus", "headache", "migraine", "cluster headache",
        "tension headache", "neuroinfections", "meningitis", "encephalitis",
        "neuropathy", "gbs", "guillain", "myasthenia", "parkinson", "tremor",
        "neurological", "neuro", "brain", "cerebral", "tpa", "alteplase", "antiepileptic",
        "phenytoin", "levetiracetam", "valproate", "carbamazepine", "infarction", "thrombolysis",
    },
    "Nephrology": {
        "kidney", "renal", "nephrology", "aki", "acute kidney injury", "ckd",
        "chronic kidney disease", "dialysis", "hemodialysis", "peritoneal dialysis",
        "glomerulonephritis", "nephrotic", "nephritic", "proteinuria", "hematuria",
        "creatinine", "urea", "egfr", "polycystic kidney", "uremia",
    },
    "Pulmonology": {
        "pulmonology", "lung", "pulmonary", "asthma", "copd", "bronchitis",
        "pneumonia", "respiratory", "wheezing", "inhaler", "salbutamol",
        "budesonide", "spirometry", "fev1", "dyspnea", "pleural effusion",
    },
    "Endocrinology": {
        "endocrinology", "diabetes", "diabetic", "glycemic", "hba1c", "insulin",
        "metformin", "thyroid", "hypothyroidism", "hyperthyroidism", "tsh",
        "cushing", "adrenal", "pituitary", "hypoglycemia", "ketoacidosis", "dka",
    },
    "Dermatology": {
        "dermatology", "skin", "eczema", "psoriasis", "dermatitis", "urticaria",
        "rash", "lesion", "pruritus", "scabies", "fungal", "tinea", "leprosy",
        "acne", "vitiligo", "bullous",
    },
    "Adult Extrapulmonary Tuberculosis": {
        "tuberculosis", "tb", "extrapulmonary", "pleural tb", "lymph node tb",
        "tubercular", "potts spine", "att", "rifampicin", "isoniazid", "pyrazinamide",
        "ethambutol",
    },
}


class SpecialtyRouter:
    """Deterministic, explainable clinical query router."""

    @classmethod
    def route_query(cls, query: str, threshold: float = 0.5) -> Tuple[Optional[str], float, Dict[str, float]]:
        """Determine target specialty based on keyword overlap.

        Returns:
            (routed_specialty, confidence, all_scores)
            If confidence < threshold, routed_specialty is None (broader search).
        """
        q_lower = query.lower()
        q_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", q_lower))
        if not q_tokens:
            return None, 0.0, {}

        scores: Dict[str, float] = {}
        for specialty, vocab in SPECIALTY_KEYWORD_MAP.items():
            matched = set()
            for term in vocab:
                if " " in term:
                    if term in q_lower:
                        matched.add(term)
                else:
                    if term in q_tokens:
                        matched.add(term)
            if matched:
                score = 0.45 + (0.15 * min(len(matched), 3))
                scores[specialty] = round(score, 3)

        if not scores:
            return None, 0.0, {}

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_spec, top_score = sorted_scores[0]

        # Check for ambiguity (two specialties with very close high score)
        if len(sorted_scores) > 1 and (top_score - sorted_scores[1][1] < 0.15) and top_score < 0.85:
            # Ambiguous routing: return None to search full corpus safely
            return None, top_score, scores

        if top_score >= threshold:
            return top_spec, top_score, scores

        return None, top_score, scores

    @classmethod
    def is_ambiguous(cls, query: str) -> bool:
        """Check if query matches multiple clinical specialties with near-equal score."""
        spec, conf, scores = cls.route_query(query, threshold=0.5)
        if spec is None and len(scores) >= 2:
            sorted_vals = sorted(scores.values(), reverse=True)
            if sorted_vals[0] >= 0.55 and (sorted_vals[0] - sorted_vals[1] < 0.12):
                return True
        return False

    @classmethod
    def get_known_specialties(cls) -> List[str]:
        """Return list of supported clinical specialties."""
        return sorted(list(SPECIALTY_KEYWORD_MAP.keys()))

    @classmethod
    def check_cross_specialty_contamination(
        cls,
        query: str,
        result_specialty: str,
    ) -> bool:
        """Return True if query explicitly belongs to another specialty than result_specialty."""
        routed_spec, conf, _ = cls.route_query(query, threshold=0.6)
        if routed_spec and routed_spec != result_specialty and conf >= 0.6:
            return True
        return False
