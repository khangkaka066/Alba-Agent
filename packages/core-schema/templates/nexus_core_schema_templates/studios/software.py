"""Blueprint C: full-stack SaaS and AI software factory (32 agents)."""

from __future__ import annotations

from nexus_core_schema.models import PathRuleSpec

from .blueprint import StudioBlueprint, StudioDepartment, StudioRole as R

SOFTWARE_FACTORY = StudioBlueprint(
    id="full-stack-software-factory", title="Full-Stack SaaS & AI Software Factory", domain="software",
    summary="32 agents plan, build and test a full-stack product with architecture, backend, frontend, data, security and E2E QA.",
    description="Directors write the product requirements, architecture decision records and artifact registry. Product, backend, frontend and data teams work in parallel; sandbox teams implement and run an end-to-end test suite; security and QA audit evidence; the gate loops failures back before sign-off.",
    tags=("software", "saas", "fullstack", "security", "e2e", "studio"),
    readiness_notes=("Code and tests run offline in an isolated container; the factory delivers source, tests and a rendered UI preview.",),
    directors=(
        R("product_director", "Product Director", "write the product requirements document with users, jobs to be done and acceptance criteria", "design/prd.md", ("report_exporter", "dynamic_team_mutator")),
        R("chief_architect", "Chief Architect", "write architecture decision records covering services, data and security", "design/adr.md", ("report_exporter", "dynamic_team_mutator")),
        R("executive_producer", "Executive Producer", "set milestones and the artifact registry mapping teams to exact files", "production/artifact_registry.json", ("report_exporter", "dynamic_team_mutator")),
    ),
    wave_one=(
        StudioDepartment("product", "Dept A · Product & UX", "turn requirements into stories and interface designs", R("product_lead", "Product Lead", "approve stories against the PRD", "design/stories.md"), (
            R("business_analyst", "Business Analyst", "write user stories with acceptance criteria", "design/stories.md", ("report_exporter",)),
            R("ux_designer", "UX Designer", "design flows and wireframes in text", "design/ux.md", ("report_exporter",)),
            R("technical_writer", "Technical Writer", "draft user and API documentation outlines", "design/docs_outline.md", ("report_exporter",)),
        ), artifacts=("design/product_review.md",)),
        StudioDepartment("backend", "Dept B · Backend & API", "specify services and endpoints", R("backend_lead", "Backend Lead", "review API contracts for consistency", "design/api_spec.md"), (
            R("api_designer", "API Designer", "write the OpenAPI-style contract", "design/api_spec.md", ("report_exporter",)),
            R("service_engineer", "Service Engineer", "specify business logic and error handling", "design/services.md", ("report_exporter",)),
            R("integration_engineer", "Integration Engineer", "specify third-party integrations and webhooks", "design/integrations.md", ("report_exporter",)),
            R("ai_engineer", "AI Engineer", "specify model calls, prompts and evaluation", "design/ai_features.md", ("report_exporter",)),
        ), artifacts=("design/backend_review.md",)),
        StudioDepartment("frontend", "Dept C · Frontend & design system", "specify the client application", R("frontend_lead", "Frontend Lead", "review component architecture", "design/frontend_spec.md"), (
            R("ui_engineer", "UI Engineer", "specify pages, components and state", "design/frontend_spec.md", ("report_exporter",)),
            R("design_system_engineer", "Design System Engineer", "define tokens, components and accessibility rules", "design/design_system.md", ("report_exporter",)),
            R("performance_engineer", "Performance Engineer", "set bundle, latency and rendering budgets", "design/performance_budget.md", ("report_exporter",)),
        ), artifacts=("design/frontend_review.md",)),
        StudioDepartment("data", "Dept D · Data & platform", "design storage and operations", R("data_lead", "Data Lead", "review schema and migrations", "design/data_model.md"), (
            R("database_engineer", "Database Engineer", "design the schema, indexes and tenant isolation", "design/data_model.md", ("report_exporter",)),
            R("devops_engineer", "DevOps Engineer", "specify environments, CI and deployment", "design/devops.md", ("report_exporter",)),
        ), artifacts=("design/data_review.md",)),
    ),
    wave_two=(
        StudioDepartment(
            "implementation", "Core implementation team", "implement the service", kind="sandbox",
            artifacts=("src/app.py", "src/models.py", "tests/test_app.py"),
            instructions="Implement a working Python service core from the PRD, API contract and data model in upstream results using only the standard library: src/models.py (data classes and validation), src/app.py (request handling functions) and tests/test_app.py (pytest tests of success and error paths). Create folders as needed.",
            review="Check validation errors are handled, tests cover failure paths and pass, and no file is a stub.",
            verification="test -s src/app.py && test -s src/models.py && python -m pytest -q tests",
        ),
        StudioDepartment(
            "e2e", "E2E automation & UI preview", "run end-to-end checks and render a UI preview", kind="sandbox",
            artifacts=("tests/e2e_flow.py", "qa/evidence/ui_preview.png"),
            instructions="Write tests/e2e_flow.py, a script that imports src.app and exercises the main user journey end to end, asserting results. Then render qa/evidence/ui_preview.png with Pillow (at least 1280x720) showing the main screen described in the frontend spec. Create folders as needed.",
            review="Run the journey, confirm assertions are meaningful and the preview shows labelled UI regions, not a blank canvas.",
            verification="python tests/e2e_flow.py && python -c \"from PIL import Image; Image.open('qa/evidence/ui_preview.png').verify()\"",
            visual_evidence=True,
        ),
    ),
    qa=StudioDepartment("qa", "QA, security & evidence audit", "verify code, tests, security and evidence", R("qa_lead", "QA Lead", "own the quality gate verdict", "qa/qa_report.md"), (
        R("security_auditor", "Security Auditor", "review the code and design for OWASP-class risks and secrets", "qa/security.md", ("report_exporter",)),
        R("code_reviewer", "Code Reviewer", "review readability, error handling and test quality", "qa/code_review.md", ("report_exporter",)),
        R("e2e_qa_engineer", "E2E QA Automation Engineer", "assess the E2E suite against acceptance criteria", "qa/e2e_assessment.md", ("report_exporter",)),
        R("accessibility_auditor", "Accessibility Auditor", "check the UI preview for contrast and structure", "qa/accessibility.md", ("report_exporter",)),
        R("evidence_auditor", "Evidence Auditor", "verify the artifact registry against files on disk", "qa/evidence_audit.md", ("report_exporter",)),
    ), artifacts=("qa/qa_report.md",)),
    release=StudioDepartment("release", "Release & packaging", "package the verified service", R("release_manager", "Release Manager", "assemble the release manifest", "release/manifest.json"), (
        R("release_engineer", "Release Engineer", "write build, run and rollback instructions", "release/README.md", ("report_exporter",)),
        R("changelog_writer", "Changelog Writer", "write the changelog and upgrade notes", "release/changelog.md", ("report_exporter",)),
    ), artifacts=("release/manifest.json",)),
    standard_wave_one=("product", "backend"), standard_wave_two="implementation",
    path_rules=(PathRuleSpec(pattern="src/**", rule="Validate every input at the boundary and return explicit errors; never log secrets."),),
)
