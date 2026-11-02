"""Blueprint B: cinematic video and brand documentary studio (26 agents)."""

from __future__ import annotations

from nexus_core_schema.models import PathRuleSpec

from .blueprint import StudioBlueprint, StudioDepartment, StudioRole as R

VIDEO_STUDIO = StudioBlueprint(
    id="cinematic-video-documentary-studio", title="Cinematic Video & Documentary Studio", domain="video",
    summary="26 agents research, script, storyboard, voice and post-produce a documentary or campaign video with a visual QA critic.",
    description="Directors fix the creative brief and production plan. Research and narrative, visual and audio departments work in parallel; a post-production sandbox compiles the storyboard and contact sheet; QA critics audit evidence before executive sign-off and delivery.",
    tags=("video", "documentary", "storyboard", "brand", "museum", "studio"),
    readiness_notes=("Moving-picture generation uses the workspace media provider through the visual department's tools; the sandbox compiles stills, storyboards and subtitle files offline.",),
    directors=(
        R("creative_director", "Creative Director", "write the creative brief: audience, message, tone and visual identity", "production/creative_brief.md", ("report_exporter", "dynamic_team_mutator")),
        R("executive_producer", "Executive Producer", "set scope, schedule and the artifact registry", "production/artifact_registry.json", ("report_exporter", "dynamic_team_mutator")),
        R("brand_guardian", "Brand Guardian", "define brand, rights and compliance constraints for every asset", "production/brand_rules.md", ("report_exporter", "dynamic_team_mutator")),
    ),
    wave_one=(
        StudioDepartment("story", "Dept A · Research & narrative", "research the subject and write the script", R("story_lead", "Narrative Lead", "approve the script structure and factual accuracy", "story/script.md"), (
            R("trend_researcher", "Trend Researcher", "research the subject and audience with sources", "story/research.md", ("web_search", "report_exporter")),
            R("historian", "Historian", "verify facts, dates and attributions", "story/fact_check.md", ("web_search", "report_exporter")),
            R("scriptwriter", "Scriptwriter", "write the narration and scene script", "story/script.md", ("report_exporter",)),
            R("localization_specialist", "Subtitle & Localisation Specialist", "write subtitles and translation notes", "story/subtitles.md", ("report_exporter",)),
        ), artifacts=("story/story_review.md",)),
        StudioDepartment("visual", "Dept B · Storyboard & visual prompts", "design shots and generation prompts", R("visual_lead", "Art & Media Director", "approve the visual language and shot list", "visual/shot_list.md"), (
            R("storyboard_artist", "Storyboard Artist", "break the script into panels with framing and duration", "visual/storyboard.md", ("report_exporter",)),
            R("visual_prompt_director", "Visual Prompt Director", "write precise image and video generation prompts per shot", "visual/prompts.md", ("media_generation", "report_exporter")),
            R("cinematographer", "Cinematographer", "specify camera, lens, lighting and movement", "visual/cinematography.md", ("report_exporter",)),
            R("colorist", "Colourist", "define the grade and palette per scene", "visual/colour.md", ("report_exporter",)),
        ), artifacts=("visual/visual_review.md",)),
        StudioDepartment("audio", "Dept C · Voice & sound", "plan narration, music and sound", R("audio_lead", "Audio & Voice Director", "approve voice, music and mix", "audio/audio_plan.md"), (
            R("voiceover_artist", "Voiceover Artist", "write the voice direction and read script with timings", "audio/voiceover.md", ("report_exporter",)),
            R("sound_designer", "Sound Designer", "specify ambience and effects per scene", "audio/sound_design.md", ("report_exporter",)),
            R("music_supervisor", "Music Supervisor", "plan the score and licensing", "audio/music.md", ("report_exporter",)),
        ), artifacts=("audio/audio_review.md",)),
    ),
    wave_two=(
        StudioDepartment(
            "postproduction", "Media post-production & compilation", "compile storyboard, subtitles and contact sheet", kind="sandbox",
            artifacts=("media/storyboard.html", "media/subtitles.srt", "qa/evidence/contact_sheet.png"),
            instructions="From the script, storyboard and subtitle text in upstream results, write media/storyboard.html (a self-contained page of panels), media/subtitles.srt (valid SRT with increasing timecodes) and render qa/evidence/contact_sheet.png with Pillow (a grid of at least six labelled panels, at least 1280x720). Create folders as needed.",
            review="Confirm the SRT timecodes are valid and monotonic, the HTML contains every panel and the contact sheet is a real grid image.",
            verification="python -c \"from PIL import Image; Image.open('qa/evidence/contact_sheet.png').verify()\" && grep -q '00:00' media/subtitles.srt",
            visual_evidence=True,
        ),
        StudioDepartment(
            "assembly", "Asset compilation & delivery pack", "build the production manifest and shot index", kind="sandbox",
            artifacts=("media/shot_index.json",),
            instructions="Write media/shot_index.json: a JSON list of shots with id, duration_seconds, prompt reference and narration line, derived from the storyboard and script in upstream results. Create folders as needed.",
            review="Validate the JSON loads, ids are unique and durations are positive numbers.",
            verification="python -c \"import json; d=json.load(open('media/shot_index.json')); assert d and len({s['id'] for s in d})==len(d)\"",
        ),
    ),
    qa=StudioDepartment("qa", "Visual QA, compliance & evidence audit", "audit every deliverable and the contact sheet", R("qa_lead", "QA Lead", "own the quality gate verdict", "qa/qa_report.md"), (
        R("visual_qa_critic", "Visual QA Critic", "inspect the contact sheet for composition, legibility and consistency", "qa/visual_critique.md", ("report_exporter",)),
        R("brand_compliance_auditor", "Brand Compliance Auditor", "check every asset against the brand and rights rules", "qa/compliance.md", ("report_exporter",)),
    ), artifacts=("qa/qa_report.md",)),
    release=StudioDepartment("release", "Release & omnichannel delivery", "package the approved production", R("release_manager", "Release Manager", "assemble the delivery manifest", "release/manifest.json"), (
        R("omnichannel_publisher", "Omnichannel Publisher", "prepare channel-specific delivery notes without publishing", "release/delivery_notes.md", ("report_exporter",)),
    ), artifacts=("release/manifest.json",)),
    standard_wave_one=("story", "visual"), standard_wave_two="postproduction",
    path_rules=(PathRuleSpec(pattern="story/**", rule="Narration states only sourced facts; mark any unverified claim as such."),),
)
