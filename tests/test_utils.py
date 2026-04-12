# tests/test_utils.py
"""Shared test utilities"""

def assert_valid_pmid(pmid: str):
    """Assert that a string is a valid PMID"""
    assert pmid.isdigit()
    assert len(pmid) >= 1 and len(pmid) <= 8

def assert_valid_nct_id(nct_id: str):
    """Assert that a string is a valid NCT ID"""
    assert nct_id.startswith("NCT")
    assert len(nct_id) == 11
    assert nct_id[3:].isdigit()

def extract_pmids_from_text(text: str) -> list[str]:
    """Extract all PMIDs from text"""
    import re
    return re.findall(r'PMID:\s*(\d+)', text)

def extract_nct_ids_from_text(text: str) -> list[str]:
    """Extract all NCT IDs from text"""
    import re
    return re.findall(r'NCT\d{8}', text)
