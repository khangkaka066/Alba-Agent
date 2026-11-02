"""Blueprint D: feature film and series production studio (50 agents), a full studio from development to release."""

from __future__ import annotations

from nexus_core_schema.models import PathRuleSpec

from .blueprint import StudioBlueprint, StudioDepartment, StudioRole as R

_DIRECTION_TOOLS = ("report_exporter", "dynamic_team_mutator")

FILM_STUDIO = StudioBlueprint(
    id="feature-film-production-studio", title="Feature Film & Series Production Studio", domain="film",
    summary="50 agents run a film studio end to end: writers' room, previsualisation, production design, camera, sound, VFX, production management, editorial, QA and release.",
    description=(
        "Three studio directors fix the vision, the director's statement and the production bible. Seven departments work in parallel "
        "like a real production: development and writers' room, direction and previsualisation, production design and casting, "
        "cinematography, sound and music, VFX and virtual production, and production management with budget and rights. Two sandbox "
        "teams assemble the animatic, edit decision list, subtitles, contact sheet, shot index and schedule. QA audits continuity, "
        "visuals and rating compliance, a quality gate sends gaps back to the responsible department, the executive producer signs off, "
        "and the distribution team prepares the release plan, trailer cut-downs and per-channel packages for TikTok, YouTube and Facebook."
    ),
    tags=("film", "movie", "series", "screenplay", "production", "studio", "trailer", "tiktok", "youtube", "facebook"),
    channels=("tiktok", "facebook", "youtube"),
    readiness_notes=(
        "Moving-picture generation uses the workspace media provider through the design departments' tools; the sandbox teams compile stills, the animatic, subtitles and manifests offline.",
        "The distribution team writes publish-ready packages for TikTok, YouTube and Facebook and stops at the executive sign-off. Connect the channels you want under Tools & Channels; direct posting is not wired to the platforms yet, so nothing is published on your behalf.",
    ),
    directors=(
        R("showrunner", "Executive Producer & Showrunner", "set the vision, the budget envelope, the schedule and the artifact registry", "production/artifact_registry.json", _DIRECTION_TOOLS),
        R("film_director", "Director", "write the director's statement: tone, visual grammar, performance and pacing", "production/directors_statement.md", _DIRECTION_TOOLS),
        R("head_of_production", "Head of Production", "define the production bible: budget bands, schedule, risks and compliance gates", "production/production_bible.md", _DIRECTION_TOOLS),
    ),
    wave_one=(
        StudioDepartment("writers_room", "Dept A · Development & writers' room", "develop the story into a treatment and a shootable screenplay",
            R("head_of_development", "Head of Development", "approve the story structure, genre positioning and logline", "story/development_review.md"), (
                R("story_analyst", "Story Analyst", "research genre, comparable titles and audience with sources", "story/market_research.md", ("web_search", "report_exporter")),
                R("screenwriter", "Screenwriter", "write the treatment and the full screenplay in scene format", "story/screenplay.md", ("report_exporter",)),
                R("dialogue_polisher", "Dialogue Polisher", "sharpen dialogue, subtext and character voice scene by scene", "story/dialogue_pass.md", ("report_exporter",)),
                R("script_doctor", "Script Doctor", "diagnose structure, pacing and act breaks and write fix notes", "story/script_notes.md", ("report_exporter",)),
            ), artifacts=("story/development_review.md",)),
        StudioDepartment("previs", "Dept B · Direction, storyboard & previsualisation", "turn the screenplay into shots, boards and a previs plan",
            R("previs_supervisor", "Storyboard & Previs Supervisor", "approve the shot list, boards and previs sequences", "visual/previs_review.md"), (
                R("first_assistant_director", "First Assistant Director", "break the screenplay into a shooting order and a scene breakdown", "visual/scene_breakdown.md", ("report_exporter",)),
                R("storyboard_artist", "Storyboard Artist", "draw the screenplay as panels with framing, movement and duration", "visual/storyboard.md", ("report_exporter",)),
                R("previs_artist", "Previs Artist", "design previsualisation for key sequences and write generation prompts", "visual/previs.md", ("media_generation", "report_exporter")),
                R("shot_designer", "Shot Designer", "write the numbered shot list with lens, angle and coverage", "visual/shot_list.md", ("report_exporter",)),
            ), artifacts=("visual/previs_review.md",)),
        StudioDepartment("art", "Dept C · Production design, costume & casting", "design the world, the wardrobe and the cast",
            R("production_designer", "Production Designer", "approve the look of every set, prop and costume", "art/design_review.md"), (
                R("art_director", "Art Director", "write the set designs and the world bible with references", "art/world_bible.md", ("report_exporter",)),
                R("set_decorator", "Set Decorator", "list the dressing, props and practical elements per set", "art/set_dressing.md", ("report_exporter",)),
                R("costume_designer", "Costume Designer", "design wardrobe per character and per scene", "art/costume_design.md", ("report_exporter",)),
                R("casting_director", "Casting Director", "write character breakdowns and casting briefs", "art/casting_briefs.md", ("report_exporter",)),
            ), artifacts=("art/design_review.md",)),
        StudioDepartment("camera", "Dept D · Cinematography & lighting", "plan how the film is photographed and lit",
            R("director_of_photography", "Director of Photography", "approve the camera, lens and lighting plan", "camera/cinematography_plan.md"), (
                R("camera_operator", "Camera Operator", "plan camera movement, rigs and operating notes per sequence", "camera/camera_plan.md", ("report_exporter",)),
                R("gaffer", "Gaffer", "design the lighting setups and power needs per set", "camera/lighting_plan.md", ("report_exporter",)),
                R("colour_scientist", "Colour Scientist", "define the colour pipeline, LUTs and the grade per scene", "camera/colour_pipeline.md", ("report_exporter",)),
                R("lens_specialist", "Lens & Optics Specialist", "specify lenses, filters and depth of field per sequence", "camera/lens_plan.md", ("report_exporter",)),
            ), artifacts=("camera/cinematography_plan.md",)),
        StudioDepartment("sound", "Dept E · Sound, music & voice", "plan dialogue, effects, score and the mix",
            R("supervising_sound_editor", "Supervising Sound Editor", "approve the sound design and the mix plan", "sound/sound_plan.md"), (
                R("dialogue_editor", "Dialogue Editor", "write the ADR and dialogue editing plan with timings", "sound/dialogue_plan.md", ("report_exporter",)),
                R("foley_artist", "Foley Artist", "specify Foley and effects per scene", "sound/foley_sheet.md", ("report_exporter",)),
                R("composer", "Composer", "write the score concept, themes and cue sheet", "sound/score_cues.md", ("report_exporter",)),
                R("music_supervisor", "Music Supervisor", "plan licensed music, clearances and temp tracks", "sound/music_plan.md", ("report_exporter",)),
            ), artifacts=("sound/sound_plan.md",)),
        StudioDepartment("vfx", "Dept F · VFX, animation & virtual production", "plan and prototype the effects work",
            R("vfx_supervisor", "VFX Supervisor", "approve the effects breakdown and the pipeline", "vfx/vfx_plan.md"), (
                R("concept_artist", "Concept Artist", "design key frames and creature or environment concepts", "vfx/concept_art.md", ("media_generation", "report_exporter")),
                R("vfx_artist", "VFX Artist", "break down every effects shot with method and complexity", "vfx/shot_breakdown.md", ("report_exporter",)),
                R("compositor", "Compositor", "plan layers, plates and compositing passes per shot", "vfx/compositing_plan.md", ("report_exporter",)),
                R("virtual_production_lead", "Virtual Production Lead", "plan LED volume, tracking and in-camera effects", "vfx/virtual_production.md", ("report_exporter",)),
            ), artifacts=("vfx/vfx_plan.md",)),
        StudioDepartment("production", "Dept G · Production management, budget & rights", "plan the money, the calendar, the locations and the clearances",
            R("line_producer", "Line Producer", "approve the budget, schedule and risk register", "production/line_producer_review.md"), (
                R("scheduler", "Production Scheduler", "build the shooting schedule from the scene breakdown", "production/shooting_schedule.md", ("report_exporter",)),
                R("budget_analyst", "Budget Analyst", "build the top-sheet budget with contingency by department", "production/budget.md", ("report_exporter",)),
                R("location_manager", "Location Manager", "list locations, permits and logistics per scene", "production/locations.md", ("report_exporter",)),
                R("rights_clearance", "Rights & Clearance Counsel", "list every clearance, release and licence the film needs", "production/clearances.md", ("web_search", "report_exporter")),
            ), artifacts=("production/line_producer_review.md",)),
    ),
    wave_two=(
        StudioDepartment(
            "edit_assembly", "Editorial assembly & animatic", "compile the animatic, edit decision list, subtitles and contact sheet", kind="sandbox",
            artifacts=("media/animatic.html", "media/edit_decision_list.json", "media/subtitles.srt", "qa/evidence/contact_sheet.png"),
            instructions=(
                "From the screenplay, storyboard and shot list in upstream results, write media/animatic.html (a self-contained page that steps through every panel with its duration), "
                "media/edit_decision_list.json (a JSON list of cuts with id, scene, in_seconds, out_seconds, transition), media/subtitles.srt (valid SRT with increasing timecodes) "
                "and render qa/evidence/contact_sheet.png with Pillow (a grid of at least six labelled panels, at least 1280x720). Create folders as needed."
            ),
            review="Confirm the SRT timecodes are valid and monotonic, the edit decision list loads with in before out, the animatic shows every panel and the contact sheet is a real grid image.",
            verification=(
                "python -c \"import json; from PIL import Image; Image.open('qa/evidence/contact_sheet.png').verify(); "
                "d=json.load(open('media/edit_decision_list.json')); assert d and all(c['in_seconds']<c['out_seconds'] for c in d)\" && grep -q '00:00' media/subtitles.srt"
            ),
            visual_evidence=True,
        ),
        StudioDepartment(
            "delivery_pack", "Shot index & production schedule pack", "build the shot index and the shooting calendar", kind="sandbox",
            artifacts=("media/shot_index.json", "production/schedule.csv"),
            instructions=(
                "Write media/shot_index.json: a JSON list of shots with id, scene, duration_seconds, camera, lens and the storyboard panel it comes from, derived from the shot list and storyboard in upstream results. "
                "Write production/schedule.csv with a header row (day,scene,location,cast,notes) and one row per shooting day derived from the scene breakdown and the shooting schedule. Create folders as needed."
            ),
            review="Validate the JSON loads with unique ids and positive durations, and that the CSV has the header and at least one data row.",
            verification=(
                "python -c \"import csv, json; d=json.load(open('media/shot_index.json')); assert d and len({s['id'] for s in d})==len(d); "
                "r=list(csv.reader(open('production/schedule.csv'))); assert r[0][:3]==['day','scene','location'] and len(r)>1\""
            ),
        ),
    ),
    qa=StudioDepartment("qa", "Continuity, visual QA & rating compliance", "audit every deliverable, the continuity and the contact sheet",
        R("qa_lead", "QA Lead", "own the quality gate verdict", "qa/qa_report.md"), (
            R("script_supervisor", "Script Supervisor", "check continuity of story, props, wardrobe and timeline across departments", "qa/continuity_report.md", ("report_exporter",)),
            R("visual_qa_critic", "Visual QA Critic", "inspect the contact sheet for composition, legibility and consistency", "qa/visual_critique.md", ("report_exporter",)),
            R("compliance_auditor", "Rating & Compliance Auditor", "check content rating, rights and safety against the production bible", "qa/compliance.md", ("report_exporter",)),
        ), artifacts=("qa/qa_report.md",)),
    release=StudioDepartment("release", "Release, distribution & social channels", "package the approved film for release",
        R("head_of_distribution", "Head of Distribution", "assemble the release manifest and the sign-off summary", "release/manifest.json"), (
            R("distribution_strategist", "Distribution Strategist", "write the release plan: windows, territories, platforms and positioning", "release/distribution_plan.md", ("report_exporter",)),
            R("trailer_editor", "Trailer Editor", "plan the trailer, teaser and 15 to 60 second cut-downs with timecodes", "release/trailer_cutdowns.md", ("report_exporter",)),
            R("social_media_manager", "Social Media Manager", "write a publish-ready package per channel (TikTok, YouTube, Facebook): title, caption, hashtags, aspect ratio, cut-down and schedule, without publishing", "release/social_packages.md", ("report_exporter",)),
        ), artifacts=("release/manifest.json",)),
    standard_wave_one=("writers_room", "previs"), standard_wave_two="edit_assembly",
    path_rules=(
        PathRuleSpec(pattern="story/**", rule="Mark any real-world fact, quote or reference as unverified unless a source is given."),
        PathRuleSpec(pattern="release/**", rule="Describe packages as ready to publish; never state that anything was posted, scheduled on a platform or approved by one."),
        PathRuleSpec(pattern="production/**", rule="Budgets, dates and legal clearances are proposals for human review, not commitments."),
    ),
)
