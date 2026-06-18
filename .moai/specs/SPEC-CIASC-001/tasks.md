## Task Decomposition
SPEC: SPEC-CIASC-001

| Task ID | Description | Requirement | Dependencies | Planned Files | Status |
|---------|-------------|-------------|--------------|---------------|--------|
| T-001 | Add CIASC_ALPHA_K env var constant to config | REQ-C-001 | - | rag/config.py | completed |
| T-002 | Add _calculate_dynamic_alpha() method to CIASCRetriever | REQ-F-001 | T-001 | rag/baseline_ciasc.py | completed |
| T-003 | Update _get_threshold() to return (threshold, alpha_used) tuple | REQ-F-001, REQ-F-005 | T-002 | rag/baseline_ciasc.py | completed |
| T-004 | Update retrieve() to include alpha_used in return dict | REQ-F-002 | T-003 | rag/baseline_ciasc.py | completed |
| T-005 | Add alpha_used: Optional[float] to ChatResult schema | REQ-F-003, REQ-C-003 | - | api/schemas.py | completed |
| T-006 | Extract alpha_used from retriever result in /chat endpoint | REQ-F-003 | T-004, T-005 | api/main.py | completed |
| T-007 | Add alpha_used to streaming meta dict in /chat/stream | REQ-F-003 | T-004 | api/main.py | completed |
| T-008 | Display α value in finalizeBotBubble() metaText (non-null guard) | REQ-F-004, REQ-C-002 | T-007 | index.html | completed |
| T-009 | Write unit tests for SC-1 through SC-7 (TDD RED-GREEN) | All REQs | T-001–T-008 | tests/test_dynamic_alpha.py | completed |
