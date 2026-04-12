# Implementation Plan: Phase 1 & 2 Enhancement

**Project:** ALS Agentic Research Agent
**Goal:** Transform from Augmented LLM to Full Agentic Agent (Evaluator-Optimizer pattern) + Add NCBI Gene & OMIM databases
**Timeline:** 8-11 days (59-87 hours)
**Status:** Planning Phase

---

## Executive Summary

This plan upgrades the ALS Research Agent through 4 stages:
1. **Core Agentic Behavior** - Implement reflection loops and planning
2. **Transparency & Polish** - Enhance visibility and self-correction
3. **NCBI Gene Server** - Add gene information database
4. **OMIM Server + Polish** - Add genetic disorder database and complete ACI improvements

**Expected Outcome:**
- Transform from single-turn to iterative multi-turn agent
- Improve Anthropic Transparency score: 3/5 → 5/5
- Improve Anthropic ACI score: 4/5 → 5/5
- Increase tool count: 7 → 11 tools
- Fill 85-100% of current agentic behavior gaps

---

## Strategic Approach

**Staged Implementation** to reduce risk and validate improvements incrementally:

- **Stage 1:** Core Agentic Behavior (Critical Path)
- **Stage 2:** Transparency & Polish
- **Stage 3:** NCBI Gene Server
- **Stage 4:** OMIM Server + ACI Polish

**Decision Points:** After Stage 1, evaluate results before proceeding to Stages 2-4.

---

## STAGE 1: Core Agentic Behavior (Phase 1 Foundation)

**Goal:** Implement Evaluator-Optimizer pattern with minimal risk
**Time Estimate:** 15-22 hours (~2-3 days)
**Priority:** CRITICAL PATH

### 1.1 Enhanced System Prompt Design (3-5 hours)

**Objective:** Design prompts that enable planning, reflection, and iteration

- [ ] Research optimal prompt patterns for multi-step reasoning
- [ ] Draft new system prompt with explicit phases:
  - PLANNING phase instructions
  - EXECUTION phase instructions
  - REFLECTION phase instructions
  - SYNTHESIS phase instructions
- [ ] Add transparency language: "Always explain your plan before tool use"
- [ ] Define stopping criteria: when to stop iterating
- [ ] Add self-assessment prompts: "Is this information sufficient?"
- [ ] Test prompt variations with simple queries
- [ ] Document prompt design decisions

**Key Question:** How many reflection loops? **Recommendation:** Start with 1 (can increase later)

**Deliverable:** New system prompt document with rationale

---

### 1.2 Planning Phase Implementation (4-6 hours)

**Objective:** Make Claude explicitly state strategy before tool use

- [ ] Modify system prompt to require explicit planning before tool use
- [ ] Format: `**PLAN:** I will [step 1], then [step 2], finally [step 3]`
- [ ] Ensure planning message streams to user (transparency)
- [ ] Test that Claude naturally produces plans without breaking flow
- [ ] Handle edge cases where Claude skips planning
- [ ] Validate planning doesn't add excessive latency

**Technical Note:** This might be pure prompt engineering, no code changes needed

**Deliverable:** Updated system prompt with planning requirement

---

### 1.3 Reflection Loop Architecture (6-8 hours)

**Objective:** Enable Claude to evaluate results and refine approach

- [ ] Design reflection loop flow:
  ```
  User Query → Plan → Execute Tools → Reflect → [Refine & Re-execute] → Synthesize
  ```
- [ ] Modify `chat_with_agent()` function in `als_agent_app.py` to support internal reflection turn
- [ ] After tool execution, inject reflection prompt:
  > "Evaluate if you have sufficient information. If not, what additional searches would help?"
- [ ] Parse Claude's reflection response to determine if refinement needed
- [ ] Implement max iteration limit (recommendation: 2-3 total cycles)
- [ ] Track state across iterations: tools used, info gathered, attempts made
- [ ] Ensure Gradio streaming works with multi-turn loop
- [ ] Add timeout safeguards (max 2 minutes total per query)

**Critical:** Test with Gradio streaming - may need to batch internal reflection turns

**Deliverable:** Modified `chat_with_agent()` with reflection loop logic

---

### 1.4 Basic Visual Formatting (2-3 hours)

**Objective:** Distinguish different agent phases visually

- [ ] Add markdown formatting for different phases:
  - `**🎯 PLAN:**` - Strategy outline
  - `**🔧 EXECUTING:**` - When calling tools
  - `**🤔 REFLECTING:**` - Evaluation phase
  - `**✅ ANSWER:**` - Final synthesis
- [ ] Test rendering in Gradio ChatInterface
- [ ] Ensure formatting doesn't break on mobile
- [ ] Keep formatting simple and professional (not gimmicky)

**Decision:** Don't over-engineer visual formatting yet - Stage 2 will polish

**Deliverable:** Basic phase markers in agent responses

---

### 1.5 Testing & Validation (4-6 hours)

**Objective:** Validate reflection improves answers without harming simple queries

**Test Cases:**

**Simple queries (should NOT trigger unnecessary reflection):**
- [ ] "Find papers on SOD1" → Should complete in 1 cycle
- [ ] "What trials for riluzole?" → Should complete in 1 cycle
- [ ] "Get details for PMID 39330700" → Should complete in 1 cycle

**Complex queries (should trigger appropriate reflection):**
- [ ] "Compare SOD1 vs C9orf72 clinical presentations" → May need 2 cycles
- [ ] "Is there contradictory evidence about tofersen efficacy?" → May need 2-3 cycles
- [ ] "Find connection between TDP-43 and mitochondrial dysfunction" → May need 2-3 cycles

**Edge cases:**
- [ ] No results found → Should try alternative search terms
- [ ] API errors → Should degrade gracefully
- [ ] Max iterations reached → Should provide best-effort answer

**Metrics:**
- [ ] Measure latency impact (baseline vs reflection loop)
- [ ] Measure token usage impact (important for costs)
- [ ] Document when reflection helps vs doesn't help

**Success Criteria:**
- ✅ Complex queries show measurable improvement in answer quality
- ✅ Simple queries don't add unnecessary latency
- ✅ User experience remains smooth with streaming

**Deliverable:** Test results document with performance metrics

---

## STAGE 2: Transparency & Polish (Phase 1 Enhancement)

**Goal:** Improve Anthropic Transparency & ACI scores
**Time Estimate:** 14-21 hours (~2-2.5 days)
**Priority:** HIGH

### 2.1 Enhanced Visual Formatting (3-4 hours)

**Objective:** Improve readability and user comprehension of agent actions

- [ ] Research Gradio advanced formatting options (Accordion, Tabs, custom CSS)
- [ ] Design cleaner phase distinctions:
  - Consider collapsible sections for tool results
  - Consider progress indicators during execution
  - Consider color coding phases (subtle)
- [ ] Implement enhanced formatting
- [ ] Test across different screen sizes
- [ ] Get user feedback on readability

**Alternative:** Could use Gradio Blocks for more control vs ChatInterface

**Deliverable:** Enhanced UI with improved visual hierarchy

---

### 2.2 Tool Call Transparency (3-4 hours)

**Objective:** Make tool usage explicit and understandable

- [ ] Make tool calls visible and distinct from responses
- [ ] Format tool calls: `**🔧 Using tool:** pubmed__search_pubmed with query='SOD1 ALS'`
- [ ] Show tool results summary: `**📊 Found:** 10 papers`
- [ ] Consider showing execution time per tool
- [ ] Make this optional/configurable (some users may want minimal UI)

**Deliverable:** Transparent tool call visualization

---

### 2.3 Self-Correction Logic (4-6 hours)

**Objective:** Enable agent to recover from poor initial results

**Detection strategies:**
- [ ] Detect poor tool results:
  - Zero results returned
  - Error messages from tools
  - Results don't match query intent (harder to detect)

**Correction strategies:**
- [ ] Implement query reformulation:
  - Try broader search terms if no results
  - Try synonyms or alternative terminology
  - Try different date ranges
- [ ] Track failed attempts to avoid repetition
- [ ] Add to reflection prompt: "Previous search for '{query}' returned no results. Try alternative approach."

**Testing:**
- [ ] Test with queries that initially fail

**Deliverable:** Self-correction mechanism in reflection loop

---

### 2.4 Enhanced Tool Descriptions (4-5 hours)

**Objective:** Improve tool selection accuracy through better documentation (ACI principle)

For each of the 7 existing tools:
- [ ] Review tool descriptions in server files
- [ ] Add 2-3 example queries per tool:
  ```python
  """Search PubMed for peer-reviewed research papers.

  Examples:
  - "Find papers on SOD1 mutations in familial ALS"
  - "What's the latest research on tofersen efficacy?"
  - "Search for TDP-43 aggregation mechanisms"

  Args:
      query: Search query (be specific for better results)
      ...
  """
  ```
- [ ] Add "Best for" and "Not suitable for" guidance
- [ ] Add parameter constraints in descriptions
- [ ] Test that improved descriptions lead to better tool selection by Claude

**Files to update:**
- `servers/pubmed_server.py`
- `servers/biorxiv_server.py`
- `servers/clinicaltrials_server.py`
- `servers/fetch_server.py`

**Deliverable:** Enhanced tool documentation across all servers

---

### 2.5 Testing & Refinement (2-4 hours)

**Objective:** Validate and iterate on enhancements

- [ ] A/B test with and without visual enhancements
- [ ] Measure user comprehension of agent actions
- [ ] Test self-correction on difficult queries
- [ ] Iterate based on findings

**Deliverable:** Refined implementation with user feedback incorporated

---

## STAGE 3: NCBI Gene Server (Phase 2 Part 1)

**Goal:** Add high-impact gene information database
**Time Estimate:** 14-20 hours (~2-2.5 days)
**Priority:** HIGH

### 3.1 API Research & Design (2-3 hours)

**Objective:** Understand NCBI Gene API and design tool interfaces

- [ ] Review NCBI Gene E-utilities documentation
- [ ] Identify required API endpoints:
  - Gene search (esearch)
  - Gene summary (esummary)
  - Gene details (efetch)
- [ ] Check rate limits (3 requests/second without API key, 10/s with key)
- [ ] Review response formats and data structure
- [ ] Design tool interfaces:
  - `search_gene(query, organism="human", max_results=10)`
  - `get_gene_details(gene_id)`
- [ ] Check for ALS-specific gene databases or resources

**Deliverable:** API design document with endpoint specifications

---

### 3.2 Build NCBI Gene Server (6-8 hours)

**Objective:** Implement working NCBI Gene MCP server

- [ ] Create `servers/ncbi_gene_server.py` using FastMCP pattern
- [ ] Implement `search_gene` tool:
  - Query NCBI Gene esearch API
  - Parse results
  - Format for Claude (gene symbols, descriptions, IDs)
- [ ] Implement `get_gene_details` tool:
  - Query NCBI Gene esummary/efetch APIs
  - Include: function, expression, pathways, orthologs
  - Format comprehensively
- [ ] Add rate limiting using shared `RateLimiter`
- [ ] Add error handling and retries
- [ ] Add response caching
- [ ] Test with real API calls for ALS genes (SOD1, C9orf72, FUS, TDP-43, TARDBP)

**Pattern to follow:** Copy structure from `pubmed_server.py` (same E-utilities API)

**Deliverable:** Working `ncbi_gene_server.py` file

---

### 3.3 Parameter Validation & Poka-Yoke (2-3 hours)

**Objective:** Implement Anthropic's poka-yoke constraints (ACI principle)

- [ ] Add strict parameter validation:
  ```python
  if max_results < 1 or max_results > 100:
      return "Error: max_results must be between 1 and 100"
  ```
- [ ] Add organism validation (human, mouse, rat most common)
- [ ] Add helpful error messages with suggestions:
  ```python
  "Gene ID must be numeric. Did you mean to use search_gene instead?"
  ```
- [ ] Add defaults for all optional parameters
- [ ] Add auto-correction where safe (capitalize gene symbols, strip whitespace)

**Deliverable:** Robust parameter validation in NCBI Gene tools

---

### 3.4 Integration & Testing (4-6 hours)

**Objective:** Integrate NCBI Gene server into main application

- [ ] Add `ncbi_gene` server to `als_agent_app.py` `setup_mcp_servers()`
- [ ] Update `shared/config.py` with NCBI rate limits
- [ ] Test NCBI Gene server via custom MCP client standalone
- [ ] Write unit tests: `tests/test_ncbi_gene_server.py`
- [ ] Integration test with full app (9 tools total)
- [ ] Test error cases (invalid IDs, rate limit, network errors)
- [ ] Verify caching works correctly

**Test queries:**
- "What is the SOD1 gene?"
- "Tell me about C9orf72 function"
- "What pathways involve TDP-43?"

**Deliverable:** Integrated NCBI Gene server with passing tests

---

## STAGE 4: OMIM Server + Final Polish (Phase 2 Part 2)

**Goal:** Add disease-gene database and complete ACI improvements
**Time Estimate:** 16-24 hours (~2-3 days)
**Priority:** MEDIUM-HIGH

### 4.1 API Research & Design (2-3 hours)

**Objective:** Understand OMIM API and design tool interfaces

- [ ] Review OMIM API documentation (may require API key)
- [ ] Check access requirements and rate limits
- [ ] Identify ALS entries in OMIM (ALS1-ALS26)
- [ ] Design tool interfaces:
  - `search_disorders(query, include_genes=True, max_results=10)`
  - `get_disorder_details(omim_id)`
- [ ] Plan genotype-phenotype linkage information

**Note:** OMIM API access might require registration - investigate early

**Deliverable:** API design document for OMIM integration

---

### 4.2 Build OMIM Server (6-8 hours)

**Objective:** Implement working OMIM MCP server

- [ ] Create `servers/omim_server.py` using FastMCP pattern
- [ ] Implement `search_disorders` tool
- [ ] Implement `get_disorder_details` tool
- [ ] Add rate limiting
- [ ] Add error handling
- [ ] Add caching
- [ ] Test with ALS-related queries

**Test queries:**
- "What genetic forms of ALS exist?"
- "What's the phenotype of FUS mutations?"
- "Tell me about ALS1"

**Deliverable:** Working `omim_server.py` file

---

### 4.3 Full Integration (3-5 hours)

**Objective:** Integrate all servers and validate system stability

- [ ] Add `omim` server to `als_agent_app.py`
- [ ] Update `shared/config.py`
- [ ] Test all 6 servers working together (11 tools total)
- [ ] Verify no conflicts or performance degradation
- [ ] Test complex queries that use multiple new tools

**Complex test query:**
> "Compare the genetic basis and clinical presentation of SOD1 vs C9orf72 ALS, including recent research and active trials"

This should use: NCBI Gene (2 calls), OMIM (2 calls), PubMed, ClinicalTrials

**Deliverable:** Fully integrated system with 11 tools

---

### 4.4 Comprehensive Parameter Validation (3-5 hours)

**Objective:** Apply poka-yoke constraints across all tools

- [ ] Review all 11 tools for parameter validation gaps
- [ ] Add validation to existing tools (PubMed, ClinicalTrials, bioRxiv, Fetch)
- [ ] Ensure consistent error message format across all servers
- [ ] Add comprehensive poka-yoke constraints:
  - Date format auto-detection
  - ID format validation with suggestions
  - Query length limits (prevent token overflow)

**Files to update:**
- `servers/pubmed_server.py`
- `servers/biorxiv_server.py`
- `servers/clinicaltrials_server.py`
- `servers/fetch_server.py`
- `servers/ncbi_gene_server.py`
- `servers/omim_server.py`

**Deliverable:** Consistent validation across all servers

---

### 4.5 Final Testing & Documentation (4-6 hours)

**Objective:** Comprehensive testing and documentation updates

**Testing:**
- [ ] Write tests for OMIM server: `tests/test_omim_server.py`
- [ ] Run full test suite for all servers
- [ ] Integration tests with complex multi-tool queries
- [ ] Performance testing with 11 tools

**Documentation:**
- [ ] Update README.md:
  - Tool count: 7 → 11
  - Add NCBI Gene tool documentation
  - Add OMIM tool documentation
  - Update architecture description (4 → 6 servers)
  - Add Phase 1 enhancements to features list
  - Update Available Tools section with examples
- [ ] Update tool examples in README with NCBI Gene and OMIM
- [ ] Document rate limits and API requirements
- [ ] Create example queries demonstrating new capabilities

**Deliverable:** Complete documentation and passing test suite

---

## Gap Analysis: What Gets Fixed?

### Current Gaps (Before Implementation)

| Gap | Status |
|-----|--------|
| Agentic loops | ❌ Single-turn responses |
| Planning phase | ❌ No explicit strategy outline |
| Self-correction | ❌ Can't revise approach |
| Reflection | ❌ No evaluation |
| Single-pass execution | ❌ One-shot only |
| Iterative refinement | ❌ No refinement loops |
| Autonomous behavior | ❌ No autonomy |

### After All Stages Complete

| Gap | Before | After | % Fixed | Notes |
|-----|--------|-------|---------|-------|
| **Agentic loops** | ❌ Single-turn | ✅ Multi-turn with reflection | **100%** | 2-3 cycle loops |
| **Planning phase** | ❌ No explicit plan | ✅ Always outlines strategy | **100%** | Explicit PLAN section |
| **Self-correction** | ❌ No retry | ✅ Can reformulate queries | **90%** | Query-level, not strategy-level |
| **Reflection** | ❌ No evaluation | ✅ "Is this sufficient?" check | **100%** | After each tool cycle |
| **Single-pass execution** | ❌ One-shot | ✅ Iterative (2-3 cycles) | **85%** | Limited by max iterations |
| **Iterative refinement** | ❌ No refinement | ✅ Refines based on results | **85%** | 1-2 strategic refinements |
| **Autonomous behavior** | ❌ No autonomy | ⚠️ Limited autonomy | **70%** | Constrained by iteration limits |

### Why Not 100% on Everything?

**Autonomy (70%):** Iteration limits (2-3 cycles) prevent fully autonomous behavior. This is **intentional** - Anthropic recommends constraints for safety and predictability.

**Iterative Refinement (85%):** Strategic 1-2 refinements, not continuous iteration. More is often worse (analysis paralysis).

**Self-Correction (90%):** Can reformulate queries but not fundamentally change research approach. Won't switch between completely different strategies.

---

## Anthropic Principles Score

### Before Implementation

1. **Simplicity:** ⭐⭐⭐⭐⭐ (5/5) - Direct API calls, no heavy frameworks
2. **Transparency:** ⭐⭐⭐ (3/5) - Streaming but no explicit planning
3. **ACI:** ⭐⭐⭐⭐ (4/5) - Good tool interfaces, minor gaps

### After Implementation

1. **Simplicity:** ⭐⭐⭐⭐⭐ (5/5) - No change, maintains simplicity
2. **Transparency:** ⭐⭐⭐⭐⭐ (5/5) - Explicit planning, tool visibility, reflection phases
3. **ACI:** ⭐⭐⭐⭐⭐ (5/5) - Examples, validation, poka-yoke constraints

### Overall Classification

**Current:** Augmented LLM (tool-using but single-turn)
**After Phase 1:** **Full Agentic Agent** (Evaluator-Optimizer pattern)
**After Phase 2:** **Enhanced Agentic Agent** with 11 specialized tools

---

## Risks & Mitigation

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Gradio streaming + reflection loops conflict | HIGH | MEDIUM | Test early in Stage 1; may need to batch internal turns |
| Increased latency (2-3x for complex queries) | MEDIUM | HIGH | Only trigger reflection when needed; show progress indicators |
| Increased token costs (2-3x) | MEDIUM | HIGH | Monitor costs; add configurable max iterations; consider Claude Haiku for reflection |
| OMIM API access restrictions | MEDIUM | LOW | Research early; have backup plan (manual curation or alternative DB) |

### Scope Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Over-engineering Phase 1 | LOW | MEDIUM | Start simple (Stage 1), validate before polish |
| Reflection doesn't help simple queries | LOW | MEDIUM | Prompt engineering to skip reflection when unnecessary |
| Visual complexity confuses users | LOW | LOW | Make formatting optional; get user feedback early |
| Stage 1 doesn't improve answers | HIGH | LOW | Extensive testing in Stage 1.5; decision point before Stage 2 |

---

## Timeline Summary

| Stage | Description | Time Estimate | Calendar Days (8hr/day) |
|-------|-------------|---------------|-------------------------|
| **Stage 1** | Core Agentic Behavior | 15-22 hours | 2-3 days |
| **Stage 2** | Transparency & Polish | 14-21 hours | 2-2.5 days |
| **Stage 3** | NCBI Gene Server | 14-20 hours | 2-2.5 days |
| **Stage 4** | OMIM + Final Polish | 16-24 hours | 2-3 days |
| **TOTAL** | | **59-87 hours** | **8-11 days** |

### Staged Milestones

**After Stage 1:**
- ✅ Have working reflection loop
- ✅ Validate approach effectiveness
- 🔍 **DECISION POINT:** Continue to Stage 2 or pivot?

**After Stage 2:**
- ✅ Have polished agentic experience
- ✅ Phase 1 complete
- ✅ Anthropic Transparency 5/5

**After Stage 3:**
- ✅ Have 9 tools (added NCBI Gene)
- ✅ Phase 2 50% complete

**After Stage 4:**
- ✅ Have 11 tools (added OMIM)
- ✅ Phase 2 100% complete
- ✅ Full agentic agent with comprehensive tool suite

---

## Success Metrics

### Stage 1 Success Criteria

**Must achieve:**
- Complex queries (requiring 3+ tools) show measurable improvement in answer quality
- Simple queries (1-2 tools) complete in ≤1.5x baseline time
- User experience remains smooth with streaming
- No critical bugs or crashes

**Nice to have:**
- 30%+ improvement on complex query quality (blind evaluation)
- <10% increase in average latency for simple queries
- Positive user feedback on transparency

### Overall Success Criteria

**Technical:**
- All 11 tools working reliably
- Response time <15 seconds for 95% of queries
- Test coverage >80%
- Zero critical security vulnerabilities

**User Experience:**
- Users understand what agent is doing (transparency)
- Agent recovers gracefully from errors
- Answers are comprehensive and well-cited

**Business:**
- Token costs increase <3x for typical usage
- System stability maintained
- Positive user feedback on new capabilities

---

## Implementation Recommendations

### Start with Stage 1

**Why Stage 1 First:**
- Validates the agentic approach quickly (15-22 hours)
- Lowest risk, highest learning
- Fills 80% of gaps for 30% of effort
- Can decide to stop or continue based on results

### After Stage 1, Evaluate:

**Questions to answer:**
1. Did reflection improve answer quality on complex queries? (measure objectively)
2. What's the latency impact? (acceptable? needs optimization?)
3. What's the cost impact? (sustainable? need Claude Haiku for reflection?)
4. Do users find it valuable? (get feedback)
5. Does reflection help or just add overhead?

### Then Decide:

**If Stage 1 succeeds:**
- ✅ Continue to Stages 2-4 as planned
- Consider accelerating timeline

**If Stage 1 has mixed results:**
- Optimize Stage 1 implementation
- Adjust Stage 2-4 scope
- Consider alternative approaches

**If Stage 1 fails to improve quality:**
- ⚠️ Pivot strategy
- Investigate why reflection didn't help
- Consider focusing on Phase 2 (more tools) instead

---

## Next Steps

1. **Review this plan** - Confirm approach and priorities
2. **Set up development branch** - Create feature branch for Phase 1
3. **Begin Stage 1.1** - Enhanced System Prompt Design
4. **Document as you go** - Keep implementation notes for learnings

---

## Appendix: Key Files to Modify

### Stage 1 (Core Agentic)
- `als_agent_app.py` - Main agent loop, reflection logic
- System prompt (in `als_agent_app.py` or separate file)

### Stage 2 (Transparency)
- `als_agent_app.py` - Enhanced formatting, self-correction
- All server files - Enhanced tool descriptions

### Stage 3 (NCBI Gene)
- `servers/ncbi_gene_server.py` - New file
- `als_agent_app.py` - Add to server setup
- `shared/config.py` - Rate limits
- `tests/test_ncbi_gene_server.py` - New file

### Stage 4 (OMIM)
- `servers/omim_server.py` - New file
- `als_agent_app.py` - Add to server setup
- `shared/config.py` - Rate limits
- `tests/test_omim_server.py` - New file
- `README.md` - Complete documentation update

---

## References

- [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- [NCBI E-utilities Documentation](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [OMIM API Documentation](https://www.omim.org/help/api)
- [Gradio Documentation](https://www.gradio.app/docs/)

---

At the end, change the description of the app to "An agentic research assistant with iterative refinement - Claude autonomously searches, reflects, and refines queries to provide comprehensive ALS research insights" or  "An autonomous AI research agent that intelligently orchestrates multiple biomedical databases to answer complex ALS research questions".

 "An agentic research assistant with iterative refinement that intelligently orchestrates multiple biomedical databases to answer complex ALS research questions".

---


