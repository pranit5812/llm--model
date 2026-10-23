# ICMR Cardiology STW Document Inventory

## Overview
This document presents the official inventory and structural analysis of all Indian Council of Medical Research (ICMR) Standard Treatment Workflow (STW) documents downloaded for the **Cardiology** specialty under Phase 1 and analyzed in Phase 2.

The source documents reside in `data/raw/cardiology/` and constitute the authoritative clinical source of truth for the project.

---

## Comparative Inventory Table

| STW ID | Condition | File Name | Pages | Document Type | ICD-11 Code | Flowcharts / Algorithms | Clinical Tables | Drug Dosages | Healthcare Delivery Tiers | Referral Criteria | Contraindications | Key References Cited |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **ICMR-CARD-001** | Atrial Fibrillation | `1768823343_cardiology_1-1.pdf` | 1 | Individual STW | BC81.31 | **Yes** (Rate vs Rhythm, Instability pathway) | **Yes** (Rate control & Anticoagulants) | **Yes** (Detailed PO/IV dosing) | **Yes** (PHC/CHC, District, Tertiary) | **Yes** (Immediate & Elective) | **Yes** (Bleeding, DOAC cautions) | ESC 2020 AF Guidelines |
| **ICMR-CARD-002** | Bradyarrhythmias in Symptomatic Patients | `1771492063_bradyarrthymia13_2_2.pdf` | 1 | Individual STW | MC81.1 | **Yes** (Stable vs Unstable algorithm) | **Yes** (Emergency drugs, PPM indications) | **Yes** (Atropine, Dopamine, Epinephrine) | **Yes** (Emergency care vs Specialist) | **Yes** (Immediate vs Pacemaker referral) | **Yes** (Sympathomimetic cautions in CAD) | ACC/AHA/HRS Guidelines |
| **ICMR-CARD-003** | Heart Failure | `1768823345_cardiology_1-3.pdf` | 1 | Individual STW | BD10 | **Yes** (GDMT initiation & titration tree) | **Yes** (Furosemide, Spironolactone, ARNI, BB, SGLT2i) | **Yes** (Starting vs target doses) | **Yes** (PHC/CHC, District, Tertiary) | **Yes** (Refractory/Advanced HF) | **Yes** (Renal/K+ cutoffs, BP limits) | 2021 ESC Heart Failure Guidelines |
| **ICMR-CARD-004** | Unstable Angina / NSTEMI | `1768823342_cardiology_1-4.pdf` | 1 | Individual STW | BA40.0 | **Yes** (ACS triage, Risk-to-cath pathway) | **Yes** (Risk strat, Revascularization timing, Drugs) | **Yes** (Loading & maintenance antiplatelets/antithrombotics) | **Yes** (PHC/CHC, District, Tertiary/PCI) | **Yes** (Time-based urgent vs early referral) | **Yes** (Prasugrel in prior stroke, bleeding) | ESC / ACC-AHA NSTE-ACS Guidelines |
| **ICMR-CARD-005** | Stable Angina | `1768823342_cardiology_1-6.pdf` | 1 | Individual STW | BA40.1 | **Yes** (Diagnostic & Anti-anginal escalation tree) | **Yes** (Essential/Other/Optional tests, Drug classes) | **Yes** (Mononitrate, NTG, CCB, Nicorandil, Ranolazine) | **Yes** (PHC/CHC, District, Tertiary) | **Yes** (Refractory angina, high-risk stress tests) | **Yes** (Nitrates in AS / PDE-5i) | 2024 ESC CCS Guidelines; 2023 ACC/AHA CCD |
| **ICMR-CARD-006** | STEMI (ST-Elevation Myocardial Infarction) | `1768823342_cardiology_1-5.pdf` | 1 | Individual STW | BA41.0 | **Yes** (Mission Lifeline reperfusion pathway) | **Yes** (Weight-based thrombolysis, general measures) | **Yes** (TNK, Alteplase, Reteplase, SK, Heparin, DAPT) | **Yes** (PCI capable vs Incapable centres) | **Yes** (Transfer <= 120m vs Thrombolysis) | **Yes** (Exhaustive absolute & relative contraindications) | ICMR STEMI / Mission Lifeline |
| **ICMR-CARD-007** | Cardiology (All) — Volume 1 Consolidated | `1771492083_cardiology_all.pdf` | 16 | Consolidated Volume | Multiple | **Yes** (Includes all 6 workflow diagrams) | **Yes** (All tables from pages 8 to 13) | **Yes** (Full compendium across all 6 conditions) | **Yes** (National 3-tier health model) | **Yes** (Universal health coverage referral matrix) | **Yes** (Consolidated contraindications) | Comprehensive national and international citations |

---

## Detailed Document Profiles

### 1. ICMR-CARD-001: Atrial Fibrillation
* **Source Document**: `1768823343_cardiology_1-1.pdf`
* **Page Count**: 1 (Information-dense visual poster)
* **Official Title**: Standard Treatment Workflow (STW) — ATRIAL FIBRILLATION
* **Coding**: ICD-11: `BC81.31`
* **Clinical Layout**:
  - **Categorization**: Paroxysmal (<7 days), Persistent (7 days to 1 year), Long-standing persistent (>1 year), Permanent (rate control only).
  - **Red Flags / Immediate Intervention**: SBP < 90 mmHg, HR > 150 or < 50 bpm, ongoing angina, CHF, TIA/stroke, major bleeding on oral anticoagulation.
  - **Investigations**:
    - Basic: Hemogram, Blood Sugar, Serum Creatinine, Electrolytes, 12-lead ECG, TSH.
    - Desirable: 2D Echocardiography, Holter monitoring.
  - **Decision Pathway**:
    - Hemodynamically unstable: Immediate DC cardioversion.
    - Hemodynamically stable: Assess Rate Control vs. Rhythm Control.
    - Anticoagulation: Stroke risk assessment via CHA2DS2-VASc score; choice between DOAC (Dabigatran, Rivaroxaban, Apixaban) and Warfarin (target INR 2.0–3.0).
  - **Medications & Dosages**:
    - Rate Control: Metoprolol (25–100 mg BD/OD), Diltiazem (30–90 mg TDS), Digoxin (0.125–0.25 mg OD), Amiodarone (100–200 mg OD), Verapamil (40–80 mg TDS).
    - Anticoagulants: Dabigatran (110/150 mg BD), Rivaroxaban (15/20 mg OD), Apixaban (2.5/5 mg BD), Warfarin (titrated to INR 2–3).
  - **Healthcare Tier Stratification**:
    - PHC/CHC: Identify AF, rate control initiation, stabilize shock, refer urgently if unstable.
    - District Hospital: Echocardiography, initiate oral anticoagulation, achieve rate control.
    - Tertiary Care: Rhythm control, cardioversion, catheter ablation, management of complex valvular AF.

---

### 2. ICMR-CARD-002: Bradyarrhythmias in Symptomatic Patients
* **Source Document**: `1771492063_bradyarrthymia13_2_2.pdf`
* **Page Count**: 1
* **Official Title**: Standard Treatment Workflow (STW) — BRADYARRTHYMIAS IN SYMPTOMATIC PATIENTS
* **Coding**: ICD-11: `MC81.1`
* **Clinical Layout**:
  - **When to Suspect**: Pulse rate < 50 bpm (persistent) accompanied by syncope, presyncope, dizziness, lethargy, fatigue, dyspnea, or chest discomfort.
  - **Basic Evaluation**: 12-lead ECG, rule out reversible causes:
    - Drug-induced: Beta-blockers, Non-DHP CCB (Verapamil, Diltiazem), Digoxin.
    - Metabolic/Endocrine: Hyperkalemia, Hypothyroidism.
    - Ischemic: Inferior wall STEMI / RV infarction.
  - **Decision Pathway**:
    - Hemodynamically Unstable (Hypotension, acute altered mental status, signs of shock, ischemic chest discomfort, acute HF):
      - First line: Atropine 0.5–1.0 mg IV bolus (repeat q3–5m, max 3 mg).
      - Second line: Dopamine infusion (2–20 mcg/kg/min) or Epinephrine infusion (2–10 mcg/min).
      - Third line / Mechanical: Transcutaneous pacing (TCP).
      - Immediate referral to facility with temporary transvenous pacing (TPI) capabilities.
    - Hemodynamically Stable:
      - Search and correct reversible etiology.
      - If irreversible and persistent high-grade AV block (Mobitz II, 3rd degree / Complete Heart Block) or symptomatic sick sinus syndrome: refer for Permanent Pacemaker (PPM) implantation.

---

### 3. ICMR-CARD-003: Heart Failure
* **Source Document**: `1768823345_cardiology_1-3.pdf`
* **Page Count**: 1
* **Official Title**: Standard Treatment Workflow (STW) — HEART FAILURE
* **Coding**: ICD-11: `BD10` (referencing 2021 ESC Guidelines)
* **Clinical Layout**:
  - **Presentation**: Dyspnea (exertional, orthopnea, PND), fatigue, bilateral pedal edema, elevated JVP, basal lung crepitations, third heart sound (S3 gallop).
  - **Investigations**:
    - Basic: Hemogram, ESR, Blood sugar, Urine analysis, Blood Urea/Serum Creatinine, Serum Sodium/Potassium, 12-lead ECG, Chest X-ray.
    - Desirable: 2D Echocardiography (LVEF assessment), NT-proBNP / BNP, Serum Troponin, Lipid profile.
  - **Pharmacotherapy & Titration Protocol**:
    - Loop Diuretic: Furosemide 20–80 mg PO daily; 10–80 mg IV SOS in acute congestion (monitor K+, creatinine, uric acid).
    - Mineralocorticoid Receptor Antagonist (MRA): Spironolactone 25–50 mg OD PO (check K+ and creatinine every 2–4 weeks).
    - ARNI (Angiotensin Receptor-Neprilysin Inhibitor): Sacubitril/Valsartan 50–200 mg BD PO (start low if SBP > 100 mmHg, normal K+, creatinine < 2.5 mg/dL; uptitrate every 1–2 weeks).
    - Beta-blockers: Carvedilol 3.125–25 mg BD PO or Metoprolol succinate 12.5–50 mg BD PO.
    - SGLT2 Inhibitors: Empagliflozin 10 mg OD PO or Dapagliflozin 10 mg OD PO.
  - **Tiered Management**:
    - PHC/CHC: Decongest with diuretics, initiate foundational therapy if stable, refer decompensated patients.
    - District Hospital: Echocardiography, initiate quadruplet GDMT, uptitrate under monitoring.
    - Tertiary Care: Advanced heart failure management, CRT/ICD evaluation, revascularization.

---

### 4. ICMR-CARD-004: Unstable Angina / NSTEMI
* **Source Document**: `1768823342_cardiology_1-4.pdf`
* **Page Count**: 1
* **Official Title**: Standard Treatment Workflow (STW) — UNSTABLE ANGINA/NSTEMI
* **Coding**: ICD-11: `BA40.0`
* **Clinical Layout**:
  - **Clinical Definition of ACS**:
    1. Angina at rest or prolonged (>20 minutes).
    2. Recent worsening of stable angina (crescendo) to CCS Class III.
    3. New-onset effort angina (<1 month) in CCS Class II/III.
    4. Post-infarction angina.
  - **ECG Stratification**:
    - ST Elevation -> Divert to STEMI STW.
    - No ST Elevation (ST depression, T wave inversion, or normal ECG) -> NSTEMI / Unstable Angina.
  - **Risk Stratification & Revascularization Strategy**:
    - **Very High Risk** (hemodynamic instability, cardiogenic shock, recurrent/refractory angina despite medical therapy, life-threatening arrhythmias, acute heart failure, mechanical complications): Immediate invasive angiography / urgent revascularization within hours.
    - **High Risk** (established rise/fall in troponin, dynamic ST-T changes, GRACE score > 140): Early invasive strategy within 24 hours.
    - **Intermediate Risk** (diabetes mellitus, renal insufficiency, prior MI, prior PCI/CABG, LVEF < 40%, GRACE 109–140): Invasive strategy within 72 hours.
    - **Low Risk**: Non-invasive risk stratification (TMT, stress imaging, CT coronary angiography).
  - **Pharmacotherapy**:
    - Antiplatelets: Aspirin loading 325 mg then 75 mg OD; Clopidogrel loading 300 mg then 75 mg OD; Prasugrel loading 60 mg then 10 mg OD; Ticagrelor loading 180 mg then 90 mg BD.
    - Antithrombotics: Enoxaparin 1 mg/kg SC q12h or UFH.
    - Anti-ischemic: High-dose Statin (Atorvastatin 80 mg OD), Metoprolol (25–100 mg), Nitrates if ongoing ischemia.

---

### 5. ICMR-CARD-005: Stable Angina
* **Source Document**: `1768823342_cardiology_1-6.pdf`
* **Page Count**: 1
* **Official Title**: Standard Treatment Workflow (STW) — STABLE ANGINA
* **Coding**: ICD-11: `BA40.1`
* **Clinical Layout**:
  - **Consider Angina If**: Diffuse retrosternal heaviness/constriction radiating to arms, neck, or back; provoked by exertion or post-meal stress; relieved by rest or sublingual NTG within 1–2 minutes.
  - **Angina Unlikely If**: Sharp/pleuritic/stabbing pain; strictly localized to a point; provoked by breathing or body movement; fleeting (<1 minute) or prolonged without relief (days).
  - **Rule Out Non-Ischemic Causes**: Aortic dissection (pulse asymmetry), pleuritis/pneumothorax, musculoskeletal pain, GERD.
  - **Investigations Triaging**:
    - Essential: Hemogram, Urea/Creatinine/Electrolytes, Fasting Glucose, Lipid Profile, Resting 12-lead ECG.
    - Other: 2D Echocardiography, Exercise Treadmill Test (TMT), Thyroid profile, HbA1c, Uric acid.
    - Optional: Stress echocardiography/radionuclide imaging, Coronary CT Angiography, Invasive Coronary Angiography (CAG), FFR/IVUS/OCT.
  - **Medical Management**:
    - Event prevention: Aspirin 75 mg OD (or Clopidogrel 75 mg), High-intensity statins (Atorvastatin 40–80 mg, Rosuvastatin 20–40 mg), ACE inhibitors (Ramipril, Enalapril).
    - Anti-anginal relief: Metoprolol short/long acting, Amlodipine (5–10 mg), Nitrates (Isosorbide mononitrate 20–60 mg), second-line options (Nicorandil 5–10 mg BD, Ranolazine 500–1000 mg BD, Trimetazidine 20 mg TDS).

---

### 6. ICMR-CARD-006: STEMI (ST-Elevation Myocardial Infarction)
* **Source Document**: `1768823342_cardiology_1-5.pdf`
* **Page Count**: 1
* **Official Title**: Standard Treatment Workflow (STW) — ST ELEVATION MYOCARDIAL INFARCTION (STEMI)
* **Coding**: ICD-11: `BA41.0`
* **Clinical Layout**:
  - **Immediate General Measures**:
    1. ICU admission with continuous cardiac monitoring and defibrillator standby.
    2. Routine biochemistry & serial cardiac troponin.
    3. Opioid analgesia for severe chest pain (Morphine 2–4 mg IV titrated q15m).
    4. Supplemental Oxygen only if SpO2 < 90%.
    5. Immediate loading doses: Aspirin 325 mg chewable, Clopidogrel 300 mg (or Ticagrelor 180 mg), Atorvastatin 80 mg.
    6. Bedside Echocardiography for wall motion and ruling out mechanical complications.
  - **Time Window Stratification**:
    - **Within 12 hours of symptom onset**: Primary reperfusion candidate.
      - If at PCI-capable hospital: Primary PCI immediately (door-to-balloon target <= 90 minutes; radial access preferred; drug-eluting stents preferred).
      - If at PCI-incapable hospital:
        - If transfer-to-PCI door-to-balloon time <= 120 minutes -> Immediate transfer for primary PCI.
        - If transfer-to-PCI > 120 minutes -> Immediate intravenous thrombolysis (door-to-needle <= 30 minutes) followed by immediate transfer to PCI facility (pharmaco-invasive strategy).
    - **12 to 24 hours**: Transfer to PCI-capable hospital; proceed with angiography/PCI if ongoing ischemia, electrical instability, or heart failure.
    - **Beyond 24 hours**: Medical stabilization; angiography with view to PCI indicated only in patients with recurrent angina, cardiogenic shock, acute pulmonary edema, mechanical complications, or dynamic ST-T changes.
  - **Thrombolytic Regimens & Dosing**:
    - Tenecteplase (TNK-tPA): Weight-based IV bolus (35 mg if 60–70 kg, 40 mg if 70–80 kg, 45 mg if > 80 kg).
    - Reteplase (r-PA): 10 U IV bolus, repeat second 10 U bolus after 30 minutes.
    - Alteplase (rt-PA): Accelerated infusion (15 mg bolus, then 0.75 mg/kg over 30 min, then 0.5 mg/kg over 60 min).
    - Streptokinase: 1.5 million units IV over 60 minutes.
  - **Contraindications to Thrombolysis**:
    - Prior intracranial hemorrhage or stroke of unknown etiology.
    - Ischemic stroke in the past 6 months.
    - CNS neoplasm or arteriovenous (AV) malformation.
    - Major trauma, surgery, or head injury within the past 1 month.
    - Major gastrointestinal bleeding within the past 1 month.
    - Known bleeding diathesis / active bleeding.
    - Suspected aortic dissection.
    - Refractory severe hypertension.

---

### 7. ICMR-CARD-007: Consolidated Volume 1 (Cardiology)
* **Source Document**: `1771492083_cardiology_all.pdf`
* **Page Count**: 16
* **Official Title**: Standard Treatment Workflows of India, 2019 Edition, Vol. 1
* **Structural Hierarchy**:
  - Pages 1–2: Title Page, Institutional Affiliation (DHR, MoHFW, ICMR), Suggested Citation.
  - Pages 3–4: Legal Disclaimers, Non-indemnity advisory notice, Web portal link (`stw.icmr.org.in`).
  - Page 5: Table of Contents.
  - Page 6: Program Introduction, UHC Goals, Evidence Methodology (Prevalence data, Global Burden of Disease, Ayushman Bharat PMJAY Health Benefit Packages, Harrison's, Oxford Handbooks).
  - Page 7: Cardiology Section Cover.
  - Pages 8–13: The 6 Clinical STW posters (Atrial Fibrillation, Bradyarrhythmias, Heart Failure, Stable Angina, Unstable Angina/NSTEMI, STEMI).
  - Page 14: National Advisory Committee Roster (Chaired by Dr. Balram Bhargava, DG ICMR; AIIMS, CMC Vellore, PGIMER, WHO Country Office).
  - Page 15: Cardiology Expert Working Group Roster (Chair: Dr. S. K. Dwivedi; AIIMS, CMC Vellore, SGPGI, JIPMER, Medanta).
  - Page 16: Volume 1 Back Cover.

---

## Recurring Clinical Concepts Identified Across Documents

Inspection of all 7 documents confirms that ICMR Cardiology STWs share a standardized clinical vocabulary and architecture:
1. **Document Identity & Classification**: Standard Treatment Workflow banner, condition title, ICD-11 code.
2. **Clinical Definition & Presentation**: Symptoms, characteristic features, atypical presentations, exclusion/alternative diagnoses.
3. **Emergency Red Flags / Immediate Indicators**: Vital instability criteria (BP < 90, severe brady/tachycardia, cardiogenic shock, acute pulmonary edema).
4. **Diagnostic Workup Stratification**:
   - Basic / Essential (available at primary/secondary tiers: ECG, Blood sugar, Urea/Creatinine, Hemogram).
   - Desirable / Other (secondary/district: Echocardiography, Troponin, TSH).
   - Optional / Advanced (tertiary: CT Angiography, Catheterization, EPS, FFR/OCT).
5. **Tiered Healthcare Delivery Network**:
   - PHC / CHC Level: Primary triage, initial stabilization, first-dose loading drugs, urgent transfer.
   - District Hospital Level: Intermediate diagnostics, admission, maintenance pharmacotherapy, non-invasive risk testing.
   - Tertiary Care / PCI Capable: Invasive interventions (PCI, CABG, ablation, permanent pacemaker, mechanical circulatory support).
6. **Decision Algorithms & Time Windows**: Time-critical decision trees (e.g. STEMI <12h vs 12-24h vs >24h; PCI vs Thrombolysis door-to-balloon thresholds).
7. **Structured Pharmacotherapy Matrices**: Exact chemical entities, dosages, routes, frequencies, loading regimens, monitoring laboratory requirements.
8. **Contraindication Profiles**: Safety exclusions (especially for thrombolysis, DOACs, anticoagulants, beta-blockers).
9. **Referral Pathways**: Specific trigger conditions dictating urgent vs. elective transfer to higher facilities.
10. **Evidence Provenance**: Citations to major guidelines (ESC, ACC/AHA) and ICMR expert consensus.
