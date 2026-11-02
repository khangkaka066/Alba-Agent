"""Blueprint F: analytics and optimisation studio (34 agents). It works from the data and reports it is given."""

from __future__ import annotations

from nexus_core_schema.models import PathRuleSpec

from .blueprint import StudioBlueprint, StudioDepartment, StudioRole as R

_DIRECTION_TOOLS = ("report_exporter", "dynamic_team_mutator")

ANALYTICS_STUDIO = StudioBlueprint(
    id="analytics-optimization-studio", title="Analytics & Optimization Studio", domain="analytics",
    summary="34 agents define measurement, diagnose performance from the data you supply, design experiments and write the report, with a statistics and privacy review.",
    description=(
        "Directors set the measurement plan and the optimisation charter. Four departments work in parallel: measurement and tracking, "
        "performance diagnosis, experiments and optimisation, and reporting. Two sandbox teams compute the KPI baseline with an HTML "
        "report and build the experiment plan and forecast. QA reviews the statistics, data privacy and the narrative, a quality gate "
        "sends gaps back, and the delivery team packages the report. Every number must come from a file you attach or be labelled an "
        "assumption: attach platform exports (CSV, spreadsheets) with the paperclip or the Hand off button."
    ),
    tags=("analytics", "kpi", "report", "experiment", "optimization", "handoff", "studio"),
    readiness_notes=(
        "Works from files you attach. Without real exports the team can only design the measurement plan and mark every figure as an assumption.",
        "It does not connect to TikTok, YouTube or Facebook analytics itself; export the reports from the platform and attach them.",
    ),
    directors=(
        R("head_of_analytics", "Head of Analytics", "set the questions to answer, the data in scope and the artifact registry", "production/artifact_registry.json", _DIRECTION_TOOLS),
        R("measurement_director", "Measurement Director", "write the measurement plan: KPIs, definitions and data sources", "production/measurement_plan.md", _DIRECTION_TOOLS),
        R("head_of_experimentation", "Head of Experimentation", "write the optimisation charter: hypotheses, guardrails and decision rules", "production/optimization_charter.md", _DIRECTION_TOOLS),
    ),
    wave_one=(
        StudioDepartment("measurement", "Dept A · Measurement & tracking", "define exactly what is measured and how",
            R("measurement_lead", "Measurement Lead", "approve the KPI definitions and data sources", "measurement/measurement_review.md"), (
                R("kpi_architect", "KPI Architect", "define each KPI, its formula and its owner", "measurement/kpi_definitions.md", ("report_exporter",)),
                R("tracking_planner", "Tracking Planner", "specify the events, parameters and tags needed to capture each KPI", "measurement/tracking_plan.md", ("report_exporter",)),
                R("data_quality_analyst", "Data Quality Analyst", "inspect the attached data for gaps, duplicates and odd values and list the fixes", "measurement/data_quality.md", ("report_exporter",)),
                R("attribution_analyst", "Attribution Analyst", "choose an attribution approach and state its limits", "measurement/attribution.md", ("report_exporter",)),
            ), artifacts=("measurement/measurement_review.md",)),
        StudioDepartment("diagnosis", "Dept B · Performance diagnosis", "find what the data says about performance",
            R("insights_lead", "Insights Lead", "approve the findings and make sure each is backed by data", "diagnosis/insights_review.md"), (
                R("funnel_analyst", "Funnel Analyst", "analyse the funnel step by step from the attached data", "diagnosis/funnel.md", ("report_exporter",)),
                R("audience_analyst", "Audience Analyst", "compare segments and where each over- or under-performs", "diagnosis/audience.md", ("report_exporter",)),
                R("content_analyst", "Content Analyst", "rank content by outcome and describe what the top items share", "diagnosis/content.md", ("report_exporter",)),
                R("anomaly_analyst", "Anomaly Analyst", "flag spikes, drops and their likely causes, marked as hypotheses", "diagnosis/anomalies.md", ("report_exporter",)),
            ), artifacts=("diagnosis/insights_review.md",)),
        StudioDepartment("experiments", "Dept C · Experiments & optimisation", "turn findings into tests and forecasts",
            R("experiment_lead", "Experiment Lead", "approve the experiment backlog and its priorities", "experiments/experiment_review.md"), (
                R("experiment_designer", "Experiment Designer", "design each test: hypothesis, variants, sample size and success rule", "experiments/designs.md", ("report_exporter",)),
                R("copy_tester", "Creative Test Planner", "plan creative and copy variants worth testing", "experiments/creative_tests.md", ("report_exporter",)),
                R("budget_optimizer", "Budget Optimiser", "propose how to shift budget between channels, with the assumptions behind it", "experiments/budget.md", ("report_exporter",)),
                R("forecaster", "Forecaster", "write a forecast with ranges and the assumptions it rests on", "experiments/forecast.md", ("report_exporter",)),
            ), artifacts=("experiments/experiment_review.md",)),
        StudioDepartment("reporting", "Dept D · Reporting & storytelling", "turn the analysis into something a decision-maker reads",
            R("reporting_lead", "Reporting Lead", "approve the report structure and the key messages", "reporting/reporting_review.md"), (
                R("report_writer", "Report Writer", "write the full report from the findings", "reporting/report.md", ("report_exporter",)),
                R("executive_summarizer", "Executive Summariser", "write a one-page summary with the three decisions to make", "reporting/executive_summary.md", ("report_exporter",)),
                R("data_visualizer", "Data Visualiser", "specify each chart: data, type, title and the takeaway it shows", "reporting/charts.md", ("report_exporter",)),
                R("recommendations_editor", "Recommendations Editor", "turn findings into ranked, owner-assigned next steps", "reporting/recommendations.md", ("report_exporter",)),
            ), artifacts=("reporting/reporting_review.md",)),
    ),
    wave_two=(
        StudioDepartment(
            "analysis_build", "KPI baseline & HTML report", "compute the baseline from the attached data and render the report", kind="sandbox",
            artifacts=("analytics/kpi_baseline.csv", "analytics/report.html"),
            instructions=(
                "Read the attached data files under upstream/ (CSV or similar). Compute the KPI baseline with the standard library and write analytics/kpi_baseline.csv "
                "with the header kpi,value,unit,source_file. If no usable data file is attached, write the header plus one row per KPI with the value 'n/a' and the source "
                "'assumption'. Then write analytics/report.html, a self-contained page with the baseline table and one inline-SVG bar chart of the numeric values. "
                "Every number must come from a file or be labelled an assumption. Create folders as needed."
            ),
            review="Confirm every value traces to a source file or is labelled as an assumption, and the HTML renders the table and chart.",
            verification="python -c \"import csv; r=list(csv.reader(open('analytics/kpi_baseline.csv'))); assert r[0][:3]==['kpi','value','unit'] and len(r)>1\" && grep -q '<svg' analytics/report.html",
            visual_evidence=False,
        ),
        StudioDepartment(
            "experiment_pack", "Experiment plan & forecast tables", "write the experiment plan and the forecast as data files", kind="sandbox",
            artifacts=("analytics/experiment_plan.json", "analytics/forecast.csv"),
            instructions=(
                "From the experiment designs and forecast notes in upstream results, write analytics/experiment_plan.json (a list of experiments with id, hypothesis, variants, "
                "metric, minimum_sample_size and decision_rule) and analytics/forecast.csv with the header period,low,expected,high,assumption. Mark every figure that is not "
                "from an attached file as an assumption. Create folders as needed."
            ),
            review="Confirm the JSON has unique ids and every forecast row names its assumption.",
            verification="python -c \"import csv, json; d=json.load(open('analytics/experiment_plan.json')); assert d and len({e['id'] for e in d})==len(d); r=list(csv.reader(open('analytics/forecast.csv'))); assert r[0][:4]==['period','low','expected','high'] and len(r)>1\"",
        ),
    ),
    qa=StudioDepartment("qa", "Statistics, privacy & narrative QA", "audit the analysis before it is delivered",
        R("qa_lead", "QA Lead", "own the quality gate verdict", "qa/qa_report.md"), (
            R("statistics_reviewer", "Statistics Reviewer", "check methods, sample sizes and whether conclusions follow from the data", "qa/statistics.md", ("report_exporter",)),
            R("data_privacy_auditor", "Data Privacy Auditor", "check that no personal data is exposed or retained without need", "qa/privacy.md", ("report_exporter",)),
            R("narrative_checker", "Narrative Checker", "check that the story matches the numbers and nothing is overstated", "qa/narrative.md", ("report_exporter",)),
        ), artifacts=("qa/qa_report.md",)),
    release=StudioDepartment("release", "Report delivery", "package the approved analysis for its readers",
        R("head_of_delivery", "Head of Reporting Delivery", "assemble the delivery manifest", "release/manifest.json"), (
            R("delivery_manager", "Delivery Manager", "write the delivery note: who receives what, and when", "release/delivery_note.md", ("report_exporter",)),
            R("stakeholder_briefer", "Stakeholder Briefer", "write the briefing script for the readout meeting", "release/briefing.md", ("report_exporter",)),
        ), artifacts=("release/manifest.json",)),
    standard_wave_one=("measurement", "diagnosis"), standard_wave_two="analysis_build",
    path_rules=(
        PathRuleSpec(pattern="analytics/**", rule="Every number comes from an attached file or is labelled an assumption; never invent data."),
        PathRuleSpec(pattern="diagnosis/**", rule="Present causes as hypotheses unless an experiment supports them."),
        PathRuleSpec(pattern="reporting/**", rule="State the data source and period for every figure."),
    ),
)
