# Cyber Insurance Research Findings

## NY DFS Cyber Insurance Risk Framework - Best Practices

### Seven Key Best Practices for Cyber Insurance Analysis:

1. **Establish formal strategy for measuring cyber risk**
   - Directed and approved by senior management and board
   - Include clear qualitative and quantitative goals for risk
   - Data-driven, comprehensive assessment approach

2. **Manage and eliminate silent cyber insurance risk**
   - Make clear whether policies provide or exclude cyber coverage
   - Mitigate existing silent risk through reinsurance

3. **Evaluate systematic risk**
   - Regular evaluation of systemic risk
   - Plan for potential catastrophic losses
   - Stress testing based on realistic catastrophic cyber events

4. **Rigorously measure insured risk**
   - Data-driven, comprehensive plan for assessing cyber risk
   - Gather information on insured's cybersecurity program
   - Assess multiple topics:
     - Incident response planning
     - Third-party security policies
     - Vulnerability management
     - Corporate governance and controls

5. **Educate insureds and insurance producers**
   - Offer comprehensive information about cybersecurity measures
   - Incentivize adoption of better cybersecurity measures
   - Price policies based on effectiveness of cybersecurity program

6. **Obtain cybersecurity expertise**
   - Recruit employees with cybersecurity experience
   - Commit to training and development
   - Supplement with consultants or vendors

7. **Require notice to law enforcement**
   - Policies should require victims to notify law enforcement

### Market Context
- 2019: $3.15 billion cyber insurance market
- 2025 (projected): $20+ billion market
- Increasing cybercrime sophistication and costs

### Ransomware Considerations
- NYDFS recommends against making ransomware payments
- Insurers must report ransom payment demands (FinCEN/OFAC obligations)

## Key Analysis Areas for Policy Evaluation

Based on framework, policy analysis should assess:
- **Incident Response Planning** - Does policy have clear IR requirements?
- **Third-Party Security Policies** - Coverage for vendor/supply chain incidents?
- **Vulnerability Management** - Requirements for security posture?
- **Corporate Governance** - Board-level oversight requirements?
- **Coverage Clarity** - Explicit inclusion/exclusion of cyber events?
- **Systematic Risk** - Policy limits vs. catastrophic event scenarios?
- **Law Enforcement Notification** - Policy requirements for reporting?


## AI Document Analysis Best Practices

### Evolution of Document Analysis Technology
1. **OCR Era** - Basic text extraction from scanned documents
2. **Rule-Based Systems** - Template-based processing with hard-coded rules
3. **ML/NLP Era** - Pattern learning from labeled examples, entity recognition
4. **IDP (Intelligent Document Processing)** - Combined OCR, ML, NLP in unified pipelines
5. **LLM/Agentic Era** - Contextual reasoning, cross-referencing, autonomous decision-making

### Modern AI Document Analysis Capabilities
- **Contextual Reasoning** - Analyze multiple documents simultaneously, cross-reference information
- **AI Citations** - Link extracted data back to exact source location for auditability
- **Workflow Integration** - API-driven integration with enterprise systems
- **Multi-Modal Processing** - Handle PDFs, scans, structured data in single ecosystem
- **Knowledge Hub** - Centralize institutional knowledge for context-specific responses

### PDF Extraction Tool Comparison

#### LlamaParse
**Strengths:**
- State-of-the-art table extraction with structural integrity
- Natural language instructions for custom parsing rules
- JSON mode for seamless pipeline integration
- Image extraction with OCR and metadata tagging
- Foreign language support (10+ file types)
- Integration with LlamaIndex for advanced RAG workflows

**Limitations:**
- Occasional text casing alterations
- May require refinement for document fidelity

**Best For:** Financial reports, contracts, multi-column layouts, multilingual documents

#### Unstructured.io
**Strengths:**
- Handles non-standard markdown structures
- Flexible integration with LangChain
- Good for diverse document types

**Limitations:**
- Struggles with layout awareness in complex documents
- May require extra formatting steps
- Less precise with intricate visual layouts

**Best For:** General-purpose extraction, LangChain integration, markdown processing

#### Vectorize
**Strengths:**
- Preserves semantic relationships
- Contextual embeddings for fragmented text
- Good for scanned documents

**Best For:** Scanned documents, context preservation, semantic analysis

### Implementation Best Practices
1. **Hybrid Approach** - Combine extractors based on document type
2. **Clear Prompts** - Provide structured instructions for AI analysis
3. **Document Structure Reference** - Guide AI with layout understanding
4. **Structured Output** - Request JSON or formatted data for downstream processing
5. **Validation & Auditability** - Implement citation tracking for compliance
6. **Adaptive Learning** - Use feedback loops to improve accuracy over time

### Key Considerations for Insurance Document Processing
- **Complex Layouts** - Multi-column, nested tables, mixed formats
- **Scanned Documents** - OCR quality critical for older policies
- **Structured Data Extraction** - Coverage limits, dates, policy numbers
- **Cross-Document Analysis** - Compare policies, benchmark against standards
- **Compliance & Auditability** - Track data lineage for regulatory requirements
- **Real-Time Processing** - Balance accuracy with speed for user experience


## Cyber Insurance Policy Evaluation Frameworks (Perplexity Research)

### Primary Frameworks Used by Insurance Industry

#### 1. NIST Cybersecurity Framework (CSF)
- **4-Tier Maturity Model**: Partial → Risk Informed → Repeatable → Adaptive
- **Five Functions**: Identify, Protect, Detect, Respond, Recover
- Used for comprehensive assessments, year-on-year comparisons, board-level reporting
- Directly influences insurance premiums and risk scores

#### 2. Cybersecurity Maturity Model Certification (CMMC 2.0)
- **Level 1**: Basic (15 controls)
- **Level 2**: Aligns with NIST SP 800-171
- **Level 3**: Enhanced with NIST SP 800-172
- Mandatory for DoD contractors, widely adopted for structured maturity paths

#### 3. CIS Controls Maturity Model
- **Levels I-V** based on implementation of 20 Critical Security Controls
- Annual agency scoring via questionnaires
- Direct correlation to insurance risk tiers

### Risk Scoring Methodologies

#### CIS-Based Cyber Insurance Risk Tiers
- **Score Range**: 1.0-5.0
- **Level V** (Optimized, CIS 1-20) = 1.0 (lowest risk)
- **Level III** (Defined, CIS 1-19) = 2.0
- **Below Level II** = 3.0+ (higher premiums)
- Non-responders default to Level 0 (highest risk)

#### Maturity Scoring (1-5 Scale)
- **1 = Initial**: Ad-hoc, reactive
- **2 = Repeatable**: Plan exists but untested
- **3 = Defined**: Documented and followed
- **4 = Managed**: Measured and controlled
- **5 = Optimized**: Continuous improvement

### Industry Benchmarks for Coverage Adequacy

| Framework | Maturity Structure | Benchmark Use |
|-----------|-------------------|---------------|
| CMMC | Levels 1-3 (Foundational to Expert) | Structured compliance for defense-related insurance |
| NIST CSF | Tiers 1-4 | Risk-based adequacy across functions |
| CIS Controls | Levels I-V | Control coverage tied to premiums |

**Minimum Standard**: Level II (Risk Score 3.0) for cyber insurance eligibility
**Gold Standard**: Level V (optimized controls)

### Common Policy Gaps Flagged in Analysis

1. **Untested Controls**
   - Incident Response plans without testing
   - Disaster Recovery procedures not validated
   - Backup restoration never verified

2. **Incomplete Assessments**
   - Unchecked NIST CSF controls
   - Partial framework coverage
   - Missing control domains

3. **Low Maturity Levels**
   - Failure to meet CIS Controls thresholds
   - Below Level II triggers higher premiums
   - Inadequate control implementation

4. **IAM Vulnerabilities**
   - Weak identity and access management
   - Insufficient people/processes/technology controls
   - 600+ NCSC/NIST factors not addressed

5. **Risk Outside Appetite**
   - Unaddressed threats to operations
   - Customer data protection gaps
   - Lacking actionable remediation plans

6. **Control Insufficiencies**
   - Partial implementation of required controls
   - Inadequate monitoring and detection
   - Insufficient response capabilities

### Assessment Process
1. **Scoping** - Define assessment boundaries
2. **Data Gathering** - Collect evidence of controls
3. **Scoring** - Rate each domain (1-5 scale)
4. **Gap Analysis** - Identify deficiencies
5. **Remediation Roadmap** - Prioritize improvements
6. **Cyber Risk Quantification (CRQ)** - Forecast financial impact

### Key Takeaways for Policy Analyzer
- Policies should be scored against NIST CSF, CMMC, and CIS Controls
- Maturity levels directly correlate to coverage adequacy
- Gap analysis should flag untested controls, incomplete assessments, and IAM vulnerabilities
- Risk scoring should use 1-5 scale with clear definitions
- Benchmarking against industry standards (Level II minimum, Level V optimal)
