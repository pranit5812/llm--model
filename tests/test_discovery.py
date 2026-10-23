"""Unit tests for STW discovery logic."""

import pytest
from bs4 import BeautifulSoup
from scripts.discover_stws import is_allowed_domain, parse_specialty_table

SAMPLE_HTML = """
<div class="card">
  <div class="card-header"><a class="btn" href="#eleven">Cardiology</a></div>
  <div class="collapse" id="eleven">
    <table class="table">
      <thead>
        <tr><th>Sr. No.</th><th>Title</th><th>Document</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>1</td>
          <td>Atrial Fibrillation</td>
          <td>
            <a href="https://www.icmr.gov.in/icmrobject/uploads/STWs/1768823343_cardiology_1-1.pdf">
              <span class="value">(43.80 KB)</span>
            </a>
          </td>
        </tr>
        <tr>
          <td>2</td>
          <td>Cardiology (All)</td>
          <td>
            <a href="https://www.icmr.gov.in/icmrobject/uploads/STWs/1771492083_cardiology_all.pdf">
              <span class="value">(7.67 MB)</span>
            </a>
          </td>
        </tr>
        <tr>
          <td>3</td>
          <td>Untrusted Doc</td>
          <td>
            <a href="https://malicious-site.com/uploads/untrusted.pdf">
              <span class="value">(1.00 MB)</span>
            </a>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
"""


def test_allowed_domain_verification():
    allowed = ["icmr.gov.in", "main.icmr.nic.in"]
    assert is_allowed_domain("https://www.icmr.gov.in/test.pdf", allowed) is True
    assert is_allowed_domain("https://main.icmr.nic.in/content/doc.pdf", allowed) is True
    assert is_allowed_domain("https://subdomain.icmr.gov.in/doc.pdf", allowed) is True
    assert is_allowed_domain("https://random-medical-site.com/doc.pdf", allowed) is False
    assert is_allowed_domain("https://icmr.gov.in.attacker.com/doc.pdf", allowed) is False


def test_parse_specialty_table():
    soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
    allowed = ["icmr.gov.in"]
    results = parse_specialty_table(
        soup=soup,
        accordion_id="eleven",
        base_url="https://www.icmr.gov.in",
        allowed_domains=allowed,
        specialty_name="Cardiology",
    )

    # 3rd row should be rejected due to non-allowed domain
    assert len(results) == 2

    # Verify individual STW
    doc1 = results[0]
    assert doc1["sequence"] == "1"
    assert doc1["title"] == "Atrial Fibrillation"
    assert doc1["document_type"] == "individual_stw"
    assert doc1["stated_size"] == "43.80 KB"
    assert "1768823343_cardiology_1-1.pdf" in doc1["pdf_url"]

    # Verify consolidated STW
    doc2 = results[1]
    assert doc2["sequence"] == "2"
    assert doc2["title"] == "Cardiology (All)"
    assert doc2["document_type"] == "consolidated_stw"
    assert doc2["stated_size"] == "7.67 MB"
