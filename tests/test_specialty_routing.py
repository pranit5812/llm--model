"""Tests for clinical specialty routing and ambiguity detection."""

import pytest
from src.retrieval.router import SpecialtyRouter


def test_cardiology_routing():
    query = "What is the recommended loading dose of aspirin in STEMI?"
    spec, conf, scores = SpecialtyRouter.route_query(query)
    assert spec == "Cardiology"
    assert conf >= 0.6


def test_neurology_routing():
    query = "Emergency management of acute ischemic stroke within window period"
    spec, conf, scores = SpecialtyRouter.route_query(query)
    assert spec == "Neurology"
    assert conf >= 0.6


def test_nephrology_routing():
    query = "Indications for urgent hemodialysis in acute kidney injury"
    spec, conf, scores = SpecialtyRouter.route_query(query)
    assert spec == "Nephrology"
    assert conf >= 0.6


def test_pulmonology_routing():
    query = "Salbutamol and budesonide inhaler dosing for severe acute asthma"
    spec, conf, scores = SpecialtyRouter.route_query(query)
    assert spec == "Pulmonology"
    assert conf >= 0.6


def test_endocrinology_routing():
    query = "Insulin therapy for diabetic ketoacidosis and severe hyperglycemia"
    spec, conf, scores = SpecialtyRouter.route_query(query)
    assert spec == "Endocrinology"
    assert conf >= 0.6


def test_ambiguous_routing():
    query = "What is the emergency thrombolysis protocol for tissue infarction?"
    assert SpecialtyRouter.is_ambiguous(query) is True


def test_unsupported_out_of_scope_routing():
    query = "Fluid replacement protocol for dengue shock syndrome"
    spec, conf, scores = SpecialtyRouter.route_query(query)
    assert spec is None or conf < 0.5
