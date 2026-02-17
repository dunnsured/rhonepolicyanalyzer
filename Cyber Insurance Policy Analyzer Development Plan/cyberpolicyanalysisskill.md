# Cyber Insurance Policy Analysis Skill

**Version:** 1.0  
**Created:** January 20, 2026  
**For:** Rhône Risk Advisory

## Overview

This skill automates Rhône Risk's complete cyber insurance policy analysis workflow, from document extraction through branded PDF report generation. It follows your comprehensive 21-section framework and implements your proprietary Superior/Average/Basic/No Coverage scoring methodology.

## What This Skill Does

**End-to-end policy analysis workflow:**
1. ✅ Extracts text from PDF or image policy documents
2. ✅ Analyzes policy against your complete 21-section framework
3. ✅ Scores coverage using your 4-tier maturity scale (Superior/Average/Basic/No Coverage)
4. ✅ Generates professionally branded HTML reports
5. ✅ Converts to PDF with Rhône Risk branding

## How to Use

### Installation

1. Download the `cyber-policy-analysis.skill` file
2. In Claude.ai, go to your Skills settings
3. Upload the `.skill` file
4. The skill will be automatically available in your conversations

### Triggering the Skill

Simply say any of these phrases:
- **"Analyze this cyber insurance policy for [Client Name]"** ← Primary trigger
- "Create a policy analysis report for [Client]"
- "Generate a cyber policy assessment"
- "Review this policy document"

Then upload the client's policy document (PDF or image format).

### What Happens Next

Claude will automatically:

1. **Extract** the policy data from your uploaded PDF/image
2. **Analyze** the policy against your comprehensive framework, including:
   - All 21 required sections
   - Every coverage type with maturity scoring
   - Red flag identification (war exclusions, patch management, etc.)
   - MSP-specific considerations (if applicable)
   - Industry benchmarking

3. **Generate** a branded PDF report with:
   - Executive summary with key metrics
   - Complete coverage analysis
   - Gap identification and recommendations
   - Rhône Risk branding and logo
   - Professional formatting

## What's Included in the Skill

### Scripts
- **extract_policy_data.py** - Extracts text from PDF/image files using pdfplumber and OCR
- **generate_report.py** - Generates branded HTML and converts to PDF using Jinja2 and WeasyPrint

### Reference Documents
- **cyber_policy_analysis_report_sections.md** - Your complete 21-section framework (all 1,750 lines)
- **coverage_scoring_guide.md** - Detailed scoring methodology for every coverage type

### Assets
- **RhoneRiskLogo1.png** - Your company logo
- **report_template.html.j2** - Your branded HTML template with Rhône color scheme

## Key Features

### Rhône Risk Scoring Methodology

The skill implements your proprietary 4-tier scoring system:

- **Superior (9-10)** - Best-in-class, exceeds industry standards
- **Average (5-8)** - Standard market terms, baseline protection
- **Basic (2-4)** - Significant limitations or gaps
- **No Coverage (0-1)** - Excluded or not mentioned

### Red Flag Detection

Automatically identifies critical issues:
- War/terrorism exclusions without buyback
- Nation-state attack exclusions
- Absolute unencrypted data exclusions
- Ransomware carve-outs
- Business interruption waiting periods >24 hours
- Social engineering sublimits <20% of aggregate
- Missing prior acts coverage

### MSP-Focused Analysis

When analyzing policies for MSP clients, the skill emphasizes:
- Third-party technology E&O
- Contingent business interruption
- Contractual liability
- Social engineering coverage

### Complete 21-Section Framework

Every analysis includes:
1. Document Header & Client Information
2. Executive Summary
3. Policy Declarations
4. Premium Structure Breakdown
5. Comprehensive Coverage Table
6. Schedule of Forms & Endorsements
7. Exclusion Analysis
8. Key Definitions Analysis
9. Critical Policy Features
10. Coverage Gap Analysis
11. Risk Quantification & Scenario Analysis
12. Benchmarking Analysis
13. Industry-Specific Considerations
14. Compliance & Regulatory Considerations
15. Recommendations & Implementation Roadmap
16. Cost-Benefit Analysis
17. Policy Terms & Conditions Review
18. Risk Management Recommendations
19. Carrier Evaluation
20. Appendices
21. Document Control

## Example Workflow

**You:** "Analyze this cyber insurance policy for Connections for Business"

*[Upload Hartford_Cyber_Policy_2026.pdf]*

**Claude:**
1. Extracts all text from the PDF
2. Analyzes against your 21-section framework
3. Scores each coverage area (Superior/Average/Basic/No Coverage)
4. Identifies red flags and gaps
5. Generates recommendations
6. Creates branded PDF report

**Result:** Professional PDF report ready for client delivery

## Technical Requirements

The skill automatically installs required Python packages:
- `pdfplumber` - PDF text extraction
- `pytesseract` - OCR for image-based PDFs
- `Pillow` - Image processing
- `jinja2` - HTML template rendering
- `pyyaml` - Data structure handling
- `weasyprint` - HTML to PDF conversion

## Customization Options

The skill is pre-configured with your:
- Complete 21-section analysis framework
- Proprietary scoring methodology
- Branded HTML template
- Company logo

If you need to update any of these, you can edit the skill files and re-upload.

## Benefits

✅ **Consistency** - Every analysis follows the same comprehensive framework  
✅ **Speed** - Automated extraction and report generation saves hours  
✅ **Quality** - No missed sections or coverage areas  
✅ **Branding** - Professional Rhône Risk presentation every time  
✅ **Accuracy** - Systematic scoring reduces subjective variation  
✅ **Scalability** - Handle more clients without expanding headcount

## Support & Iteration

This skill can be updated and improved based on your feedback:
- Add new coverage types
- Modify scoring criteria
- Update report template
- Enhance analysis logic
- Add industry-specific templates

Simply provide feedback after using the skill and we can refine it together.

## Version History

**v1.0 - January 20, 2026**
- Initial release
- Complete 21-section framework implementation
- Superior/Average/Basic/No Coverage scoring
- End-to-end workflow automation
- Rhône Risk branding integration

---

**Questions or Issues?**

Let me know if you encounter any issues or have suggestions for improvements. The skill is designed to be iterative and can be enhanced based on your real-world usage.
