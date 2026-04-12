# tests/conftest.py
import pytest
import asyncio
import sys
from typing import AsyncGenerator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def pubmed_session() -> AsyncGenerator[ClientSession, None]:
    """Create a test session for PubMed MCP server"""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["servers/pubmed_server.py"]
    )
    
    async with stdio_client(server_params) as (read, write):
        session = ClientSession(read, write)
        await session.initialize()
        yield session

@pytest.fixture
async def clinicaltrials_session() -> AsyncGenerator[ClientSession, None]:
    """Create a test session for ClinicalTrials MCP server"""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["servers/clinicaltrials_server.py"]
    )
    
    async with stdio_client(server_params) as (read, write):
        session = ClientSession(read, write)
        await session.initialize()
        yield session

@pytest.fixture
async def fetch_session() -> AsyncGenerator[ClientSession, None]:
    """Create a test session for Fetch MCP server"""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["servers/fetch_server.py"]
    )

    async with stdio_client(server_params) as (read, write):
        session = ClientSession(read, write)
        await session.initialize()
        yield session

@pytest.fixture
async def biorxiv_session() -> AsyncGenerator[ClientSession, None]:
    """Create a test session for bioRxiv MCP server"""
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["servers/biorxiv_server.py"]
    )

    async with stdio_client(server_params) as (read, write):
        session = ClientSession(read, write)
        await session.initialize()
        yield session

@pytest.fixture
def mock_pubmed_response():
    """Mock PubMed API XML response"""
    return """<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2019//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_190101.dtd">
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
      <PMID Version="1">12345678</PMID>
      <Article PubModel="Print">
        <ArticleTitle>Novel SOD1-targeted therapy for ALS treatment</ArticleTitle>
        <Abstract>
          <AbstractText>This study investigates a novel therapeutic approach targeting SOD1 mutations in ALS patients.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author ValidYN="Y">
            <LastName>Smith</LastName>
            <ForeName>John</ForeName>
          </Author>
          <Author ValidYN="Y">
            <LastName>Doe</LastName>
            <ForeName>Jane</ForeName>
          </Author>
        </AuthorList>
      </Article>
      <PubDate>
        <Year>2024</Year>
        <Month>05</Month>
      </PubDate>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""

@pytest.fixture
def mock_clinicaltrials_response():
    """Mock ClinicalTrials.gov API response"""
    return {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT12345678",
                        "briefTitle": "Phase 3 Trial of Novel ALS Drug"
                    },
                    "statusModule": {
                        "overallStatus": "RECRUITING"
                    },
                    "descriptionModule": {
                        "briefSummary": "This is a randomized, double-blind study evaluating the efficacy of a novel compound in ALS patients."
                    }
                }
            }
        ]
    }

@pytest.fixture
def mock_biorxiv_response():
    """Mock bioRxiv/medRxiv API response"""
    return {
        "collection": [
            {
                "doi": "10.1101/2024.01.15.123456",
                "title": "Novel therapeutic targets in ALS: A comprehensive review",
                "abstract": "This study investigates new therapeutic approaches for ALS treatment targeting multiple pathways.",
                "authors": "Smith J; Doe J; Johnson K; Williams L",
                "date": "2024-01-15",
                "category": "Neuroscience",
                "version": "1",
                "license": "CC BY 4.0"
            },
            {
                "doi": "10.1101/2024.01.10.789012",
                "title": "TDP-43 aggregation mechanisms in ALS pathology",
                "abstract": "We describe novel mechanisms of TDP-43 protein aggregation in motor neurons.",
                "authors": "Brown M; Taylor R",
                "date": "2024-01-10",
                "category": "Molecular Biology",
                "version": "2",
                "license": "CC BY-NC 4.0"
            }
        ]
    }
