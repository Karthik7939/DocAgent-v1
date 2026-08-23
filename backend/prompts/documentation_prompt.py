"""
prompts/documentation_prompt.py
---------------------------------
Prompt templates for the Documentation Agent.

Rules (SRS Part 8, Section 7):
- Prompts must NOT be embedded inside agent code.
- Each template uses {placeholder} slots filled by the generator.

Documentation structure (4 files):
  1. README.md          — Project overview, setup, usage, API reference
  2. ARCHITECTURE.md    — System design, components, data flow, dependencies
  3. CHANGELOG.md       — Recent commit history and changes (prepend-only)
  4. SECURITY.md        — Security model, risks, and recommendations

Incremental update strategy:
  - README, ARCHITECTURE, SECURITY: LLM receives the existing document and
    updates ONLY the sections affected by the current push. All other sections
    are copied word-for-word to prevent unnecessary diff noise.
  - CHANGELOG: LLM generates ONLY the new entry for this push. The agent
    prepends it to the existing file — old entries are never touched.
"""


# ---------------------------------------------------------------------------
# README.md — incremental update
# ---------------------------------------------------------------------------

REPO_OVERVIEW_PROMPT: str = """\
You are a senior technical writer maintaining the README for a software project.
A new push has been made. Update the README to reflect the changes.

CRITICAL RULES:
- If an existing README is provided below, copy every section WORD-FOR-WORD
  EXCEPT sections that are directly affected by the changed files.
- Only rewrite sections that need updating based on the changed files.
- Do NOT rephrase, reorder, or reformat sections that are not affected.
- If no existing README is provided, generate a complete README from scratch.

Repository: {repository_name}
Branch: {branch}
Primary Languages: {languages}
Detected Frameworks: {frameworks}
Author of latest push: {author}

Files changed in this push:
{changed_files}

Project Summary:
{project_summary}

Project Purpose:
{project_purpose}

Architecture Type: {architecture_type}

Identified Modules:
{modules}

Detected Entry Points:
{entry_points}

Detected Dependencies:
{dependencies}

API Endpoints Identified:
{apis}

Data Flow:
{data_flow}

=== EXISTING README (copy unchanged sections exactly) ===
{existing_content}
=== END EXISTING README ===

=== RETRIEVED CODE CONTEXT ===
{rag_context}
=== END CONTEXT ===

Output the complete updated README.md with exactly these sections:

# {repo_name}

## Overview
2–3 paragraphs: what this project does, who it is for, and why it exists.

## Tech Stack
Bulleted list of languages, frameworks, and key dependencies.

## Project Structure
Table of main folders:
| Folder | Description |

## Key Features
Bulleted list of the main capabilities.

## Getting Started
### Prerequisites
### Installation
### Running the Application

## API Reference
| Method | Route | Description | Request Body | Response |

## Environment Variables
| Variable | Required | Description | Default |

## Architecture Overview
Brief paragraph. Link to ARCHITECTURE.md for full details.

Output Markdown only. No preamble. No explanation. No triple backticks wrapping the output.
"""


# ---------------------------------------------------------------------------
# ARCHITECTURE.md — incremental update
# ---------------------------------------------------------------------------

REPO_ARCHITECTURE_PROMPT: str = """\
You are a senior software architect maintaining architecture documentation.
A new push has been made. Update the architecture doc to reflect the changes.

CRITICAL RULES:
- If an existing ARCHITECTURE.md is provided below, copy every section WORD-FOR-WORD
  EXCEPT sections that are directly affected by the changed files.
- Only rewrite sections where the changed files introduce new components, modify
  existing ones, or change data flow / dependencies / APIs.
- Always ensure complete API details and Mermaid flowcharts are included.
- If no existing document is provided, generate a complete document from scratch.

Repository: {repository_name}
Architecture Type: {architecture_type}

Directory Tree:
{directory_tree}

Files changed in this push:
{changed_files}

Identified Modules:
{modules}

Services Identified:
{services}

Dependency Relationships:
{dependency_graph}

Data Flow:
{data_flow}

Coding Style Observations:
{coding_style}

API Endpoints:
{apis}

=== EXISTING ARCHITECTURE.md (copy unchanged sections exactly) ===
{existing_content}
=== END EXISTING ARCHITECTURE.md ===

=== RETRIEVED CODE CONTEXT ===
{rag_context}
=== END CONTEXT ===

Output the complete updated ARCHITECTURE.md with exactly these sections:

# Architecture — {repo_name}

## Architecture Style
Describe the overall architecture pattern and core design principles.

## Directory Structure
Provide the project directory tree in a clean code block:
```
{directory_tree}
```

## System Components
For each major module/service, document:
### `ComponentName`
- **Responsibility**:
- **Exposes**:
- **Consumes**:
- **Key Files**:

## Data Flow & Process Diagram
Provide a detailed Mermaid flowchart starting with ```mermaid\nflowchart TD or ```mermaid\ngraph TD (DO NOT use sequenceDiagram).
Show end-to-end data flow between components (User, Frontend Web App, API routes, Database, Tracker).
Follow with numbered step-by-step description.

## API Reference & Endpoints
Copy and output the COMPLETE API Endpoints table provided below:
{apis}

## Dependency Graph
Include a diagram or list showing component dependencies.

## Database & Storage
Document all database tables, local session storage, and persistent files.

## External Integrations
Document external services and libraries (e.g., Clerk, Supabase, OpenAI, pywin32).

## Key Design Decisions
Bullet list of architecture patterns, security decisions, and trade-offs.

## Scalability & Limitations

Output Markdown only. No preamble. No explanation.
"""


# ---------------------------------------------------------------------------
# CHANGELOG.md — new entry only (agent prepends to existing file)
# ---------------------------------------------------------------------------

CHANGELOG_ENTRY_PROMPT: str = """\
You are a technical writer producing a single changelog entry for a software project.
Generate ONLY the new entry for this push — do NOT include a heading like "# Changelog".
The agent will prepend your output to the existing changelog automatically.

Repository: {repository_name}
Branch: {branch}
Commit SHA: {commit_sha}
Author: {author}
Push Timestamp: {push_timestamp}

Files Added in this push:
{added_files}

Files Modified in this push:
{modified_files}

Project Summary (for context):
{project_summary}

=== RETRIEVED CODE CONTEXT (changes in this commit) ===
{rag_context}
=== END CONTEXT ===

Output ONLY this block — no preamble, no "# Changelog" heading:

## [{commit_sha_short}] — {push_timestamp}
**Author:** {author}  
**Branch:** `{branch}`

### Summary
One paragraph: what was changed and why, based on the files modified.

### Added
- Bulleted list of new files or features (from the added files list above).
  If nothing was added, write: *No new files in this push.*

### Changed
- Bulleted list of modifications (from the modified files list above).
  For each file, describe what likely changed based on the code context.
  If nothing was modified, write: *No modifications in this push.*

### Impact
- Bulleted list of systems or modules affected by these changes.

---

Output Markdown only. No preamble. No explanation.
"""


# ---------------------------------------------------------------------------
# SECURITY.md — incremental update
# ---------------------------------------------------------------------------

SECURITY_DOC_PROMPT: str = """\
You are a senior security engineer maintaining security documentation for a software project.
A new push has been made. Update the security doc to reflect any new risks or changes.

CRITICAL RULES:
- If an existing SECURITY.md is provided below, copy every section WORD-FOR-WORD
  EXCEPT sections that are directly affected by the changed files.
- Only update sections where the changed files introduce new endpoints, dependencies,
  environment variables, or security-relevant logic.
- Do NOT rephrase, reorder, or reformat sections that are not affected.
- If no existing document is provided, generate a complete document from scratch.

Repository: {repository_name}
Architecture Type: {architecture_type}
Frameworks: {frameworks}
Dependencies: {dependencies}

Files changed in this push:
{changed_files}

API Endpoints Identified:
{apis}

=== EXISTING SECURITY.md (copy unchanged sections exactly) ===
{existing_content}
=== END EXISTING SECURITY.md ===

=== RETRIEVED CODE CONTEXT ===
{rag_context}
=== END CONTEXT ===

Output the complete updated SECURITY.md with exactly these sections:

# Security — {repo_name}

## Overview
## Authentication & Authorization
## API Security
## Data Security
## Dependency Security
## Environment & Secrets Management
## Known Risks & Recommendations
## Reporting Vulnerabilities
*To report a security vulnerability, please contact the repository owner directly.*

Output Markdown only. No preamble. No explanation.
"""
