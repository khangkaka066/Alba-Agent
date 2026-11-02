"""Blueprint E: marketing and social publishing studio (41 agents). It starts from what an earlier team produced."""

from __future__ import annotations

from nexus_core_schema.models import PathRuleSpec

from .blueprint import StudioBlueprint, StudioDepartment, StudioRole as R

_DIRECTION_TOOLS = ("report_exporter", "dynamic_team_mutator")

MARKETING_STUDIO = StudioBlueprint(
    id="marketing-social-publishing-studio", title="Marketing & Social Publishing Studio", domain="marketing",
    summary="41 agents turn finished work (a film, a report, a product) into a campaign: strategy, creative, per-channel packages for TikTok, YouTube and Facebook, brand safety and a launch plan.",
    description=(
        "Directors set the campaign goal, the creative direction and the compliance gates. Five departments work in parallel: audience "
        "and strategy, creative and copy, channel packaging, paid media and discovery, and brand safety with rights and platform policy. "
        "Two sandbox teams build the content calendar, the per-channel packages and a KPI tracker. QA checks copy, brand safety and "
        "platform policy, a quality gate sends gaps back to the responsible department, the head of growth signs off, and the launch "
        "team writes the launch plan and a publishing checklist. The team reads the files handed over from the earlier team "
        "(script, storyboard, video) instead of recreating them."
    ),
    tags=("marketing", "campaign", "social", "launch", "tiktok", "youtube", "facebook", "handoff", "studio"),
    channels=("tiktok", "facebook", "youtube"),
    readiness_notes=(
        "Starts from the files an earlier team handed over; attach them with the paperclip or the Hand off button.",
        "The team writes publish-ready packages and stops at the sign-off. Connect channels under Settings → Integrations; direct posting to the platforms is not wired yet, so nothing is posted on your behalf.",
    ),
    directors=(
        R("chief_marketing_officer", "Chief Marketing Officer", "set the campaign goal, audience, budget envelope and the artifact registry", "production/artifact_registry.json", _DIRECTION_TOOLS),
        R("creative_director", "Creative Director", "write the creative direction: message, tone, visual identity and hooks", "production/creative_direction.md", _DIRECTION_TOOLS),
        R("head_of_growth", "Head of Growth & Compliance", "define success metrics, brand-safety rules and approval gates", "production/growth_charter.md", _DIRECTION_TOOLS),
    ),
    wave_one=(
        StudioDepartment("strategy", "Dept A · Audience & strategy", "understand the audience and position the campaign",
            R("head_of_strategy", "Head of Strategy", "approve the audience, positioning and the measurable goals", "strategy/strategy_review.md"), (
                R("audience_researcher", "Audience Researcher", "describe the audience segments and what each cares about, with sources", "strategy/audience.md", ("web_search", "report_exporter")),
                R("competitor_analyst", "Competitor Analyst", "review how comparable work is promoted and where the gaps are", "strategy/competitors.md", ("web_search", "report_exporter")),
                R("positioning_strategist", "Positioning Strategist", "write the positioning, key messages and proof points from the handed-over material", "strategy/positioning.md", ("report_exporter",)),
                R("kpi_planner", "KPI Planner", "set targets per channel and how each will be measured", "strategy/kpi_plan.md", ("report_exporter",)),
            ), artifacts=("strategy/strategy_review.md",)),
        StudioDepartment("creative", "Dept B · Creative & copy", "write the words and plan the visuals for every channel",
            R("creative_lead", "Creative Lead", "approve the copy and the visual concepts", "creative/creative_review.md"), (
                R("copywriter", "Copywriter", "write headlines, captions and descriptions in the brand voice", "creative/copy_deck.md", ("report_exporter",)),
                R("hook_writer", "Hook Writer", "write the first three seconds of each short-form video, with alternatives", "creative/hooks.md", ("report_exporter",)),
                R("cutdown_editor", "Cut-down Planner", "plan 15, 30 and 60 second cut-downs from the handed-over script and footage, with timecodes", "creative/cutdowns.md", ("report_exporter",)),
                R("thumbnail_art_director", "Thumbnail Art Director", "design thumbnails and key art and write their generation prompts", "creative/thumbnails.md", ("media_generation", "report_exporter")),
                R("localization_specialist", "Localisation Specialist", "adapt copy and subtitles for the main audience languages", "creative/localisation.md", ("report_exporter",)),
            ), artifacts=("creative/creative_review.md",)),
        StudioDepartment("channels", "Dept C · Channel packaging", "fit the campaign to each platform's format and culture",
            R("head_of_channels", "Head of Channels", "approve the per-channel plan", "channels/channel_review.md"), (
                R("tiktok_specialist", "TikTok Specialist", "write the TikTok package: format, caption, hashtags, sounds and posting times", "channels/tiktok.md", ("report_exporter",)),
                R("youtube_specialist", "YouTube Specialist", "write the YouTube package: title, description, chapters, tags and Shorts plan", "channels/youtube.md", ("report_exporter",)),
                R("facebook_specialist", "Facebook Specialist", "write the Facebook package: post copy, reels plan and page schedule", "channels/facebook.md", ("report_exporter",)),
                R("community_manager", "Community Manager", "plan replies, moderation rules and community prompts", "channels/community.md", ("report_exporter",)),
            ), artifacts=("channels/channel_review.md",)),
        StudioDepartment("paid_discovery", "Dept D · Paid media & discovery", "plan paid reach, search and partnerships",
            R("head_of_acquisition", "Head of Acquisition", "approve the paid and discovery plan and its budget split", "paid/acquisition_review.md"), (
                R("paid_media_buyer", "Paid Media Buyer", "plan paid campaigns per channel with budget, audiences and bidding", "paid/media_plan.md", ("report_exporter",)),
                R("seo_specialist", "SEO Specialist", "research keywords and write the search and metadata plan", "paid/seo.md", ("web_search", "report_exporter")),
                R("partnership_manager", "Partnership Manager", "list creators and partners to approach and the outreach message", "paid/partnerships.md", ("web_search", "report_exporter")),
                R("email_crm_specialist", "Email & CRM Specialist", "plan the email and CRM sequence that supports the launch", "paid/crm_sequence.md", ("report_exporter",)),
            ), artifacts=("paid/acquisition_review.md",)),
        StudioDepartment("compliance", "Dept E · Brand safety, rights & policy", "keep the campaign safe, licensed and within platform rules",
            R("head_of_compliance", "Head of Compliance", "approve the brand-safety and rights position", "compliance/compliance_review.md"), (
                R("brand_guardian", "Brand Guardian", "check every message and visual against the brand rules", "compliance/brand_check.md", ("report_exporter",)),
                R("rights_clearance", "Rights & Clearance Counsel", "list music, footage, likeness and quotation rights each asset needs", "compliance/rights.md", ("web_search", "report_exporter")),
                R("platform_policy_reviewer", "Platform Policy Reviewer", "check each package against the platform's advertising and content policies", "compliance/platform_policy.md", ("web_search", "report_exporter")),
                R("accessibility_reviewer", "Accessibility Reviewer", "check captions, contrast and plain-language requirements", "compliance/accessibility.md", ("report_exporter",)),
            ), artifacts=("compliance/compliance_review.md",)),
    ),
    wave_two=(
        StudioDepartment(
            "calendar_build", "Content calendar & channel packages", "turn the plans into a calendar and one package per channel", kind="sandbox",
            artifacts=("marketing/content_calendar.csv", "marketing/channel_packages.json"),
            instructions=(
                "From the strategy, copy and channel plans in upstream results, write marketing/content_calendar.csv with the header "
                "date,channel,format,title,caption,asset (one row per planned post, dates in ISO format, channel one of tiktok, youtube, facebook) "
                "and marketing/channel_packages.json: an object with the keys tiktok, youtube and facebook, each holding title, caption, hashtags, "
                "aspect_ratio and the names of the handed-over files it uses. Never claim that anything was posted. Create folders as needed."
            ),
            review="Confirm the CSV has the header and valid ISO dates and channels, and the JSON has the three channels with non-empty captions.",
            verification=(
                "python -c \"import csv, json; r=list(csv.reader(open('marketing/content_calendar.csv'))); assert r[0][:3]==['date','channel','format'] and len(r)>1; "
                "d=json.load(open('marketing/channel_packages.json')); assert {'tiktok','youtube','facebook'} <= set(d) and all(d[k].get('caption') for k in ('tiktok','youtube','facebook'))\""
            ),
        ),
        StudioDepartment(
            "kpi_tracker", "KPI tracker & report template", "build the tracker the team will fill in after launch", kind="sandbox",
            artifacts=("marketing/kpi_tracker.csv", "marketing/report_template.html"),
            instructions=(
                "Write marketing/kpi_tracker.csv with the header metric,channel,target,unit,week_1,week_2,week_3,week_4 and one row per KPI in the KPI plan "
                "(leave the weekly cells empty), and marketing/report_template.html, a self-contained page with a table for the tracker and empty sections "
                "for what worked, what did not and next steps. Do not invent results. Create folders as needed."
            ),
            review="Confirm the CSV header and rows match the KPI plan and the HTML is self-contained with no invented numbers.",
            verification="python -c \"import csv; r=list(csv.reader(open('marketing/kpi_tracker.csv'))); assert r[0][:4]==['metric','channel','target','unit'] and len(r)>1\" && grep -q '<table' marketing/report_template.html",
        ),
    ),
    qa=StudioDepartment("qa", "Copy, brand-safety & platform QA", "audit every deliverable before sign-off",
        R("qa_lead", "QA Lead", "own the quality gate verdict", "qa/qa_report.md"), (
            R("copy_editor", "Copy Editor", "check spelling, tone and consistency of all copy", "qa/copy_edit.md", ("report_exporter",)),
            R("brand_safety_auditor", "Brand Safety Auditor", "check every asset and message for brand-safety risks", "qa/brand_safety.md", ("report_exporter",)),
            R("channel_policy_auditor", "Channel Policy Auditor", "check each package against the platform policies once more", "qa/channel_policy.md", ("report_exporter",)),
        ), artifacts=("qa/qa_report.md",)),
    release=StudioDepartment("release", "Launch & publishing checklist", "package the approved campaign for launch",
        R("head_of_launch", "Head of Launch", "assemble the launch manifest and sign-off summary", "release/manifest.json"), (
            R("launch_manager", "Launch Manager", "write the launch plan: sequence, owners and the first 72 hours", "release/launch_plan.md", ("report_exporter",)),
            R("publishing_coordinator", "Publishing Coordinator", "write the per-channel publishing checklist a person follows to post, without posting anything", "release/publishing_checklist.md", ("report_exporter",)),
            R("community_playbook_writer", "Community Playbook Writer", "write the reply and escalation playbook for launch week", "release/community_playbook.md", ("report_exporter",)),
        ), artifacts=("release/manifest.json",)),
    standard_wave_one=("strategy", "creative"), standard_wave_two="calendar_build",
    path_rules=(
        PathRuleSpec(pattern="release/**", rule="Describe packages as ready to publish; never state that anything was posted, scheduled on a platform or approved by one."),
        PathRuleSpec(pattern="strategy/**", rule="Audience and market claims need a source; mark every projection as a projection."),
        PathRuleSpec(pattern="marketing/**", rule="Targets are goals, not results; never invent performance numbers."),
    ),
)
