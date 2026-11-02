"""Blueprint A: full game development studio (49 agents)."""

from __future__ import annotations

from nexus_core_schema.models import PathRuleSpec

from .blueprint import StudioBlueprint, StudioDepartment, StudioRole as R

GAME_STUDIO = StudioBlueprint(
    id="full-game-development-studio", title="Full Game Development Studio", domain="game",
    summary="49 agents in three tiers build a playable game with design, narrative, art, audio, engine code, tests and visual QA evidence.",
    description="Directors write the game design document, technical architecture and artifact registry. Five departments work in parallel, two sandbox teams implement and compile the game, a QA crew inspects evidence, a quality gate loops failures back to the responsible department, and an executive sign-off precedes release.",
    tags=("game", "design", "phaser", "godot", "qa", "studio"),
    readiness_notes=("Sandbox code runs offline in an isolated Python container; the studio delivers a browser-playable web build and exports.", "Rendered previews are produced by the build sandbox and saved to qa/evidence/."),
    directors=(
        R("creative_director", "Creative Director", "guard the vision and write the game design document with pillars, core loop, target audience and scope", "design/gdd.md", ("report_exporter", "dynamic_team_mutator")),
        R("technical_director", "Technical Director", "choose the engine, define the architecture and write an architecture decision record", "design/architecture.md", ("report_exporter", "dynamic_team_mutator")),
        R("executive_producer", "Executive Producer", "define milestones, risks and the artifact registry mapping every department to its exact files", "production/artifact_registry.json", ("report_exporter", "dynamic_team_mutator")),
    ),
    wave_one=(
        StudioDepartment("design", "Dept A · Design, systems & UX", "design the rules, economy, levels and interface", R("design_lead", "Design Lead", "review specialist designs for coherence with the pillars", "design/systems.md"), (
            R("systems_designer", "Systems Designer", "specify the core loop, mechanics and progression rules", "design/systems.md", ("report_exporter",)),
            R("economy_designer", "Economy Designer", "model resources, rewards and balance curves", "design/economy.md", ("chart_generator", "report_exporter")),
            R("level_designer", "Level Designer", "lay out levels, pacing and difficulty ramps", "design/levels.md", ("report_exporter",)),
            R("ux_designer", "UX Designer", "design flows, HUD, menus and accessibility", "design/ux.md", ("report_exporter",)),
            R("combat_designer", "Combat Designer", "specify enemy behaviours, encounters and player abilities", "design/encounters.md", ("report_exporter",)),
            R("prototyper", "Prototyper", "define the smallest playable prototype and its success test", "design/prototype_plan.md", ("report_exporter",)),
        ), artifacts=("design/design_review.md",)),
        StudioDepartment("narrative", "Dept B · Narrative & localisation", "write story, characters, dialogue and localised text", R("narrative_lead", "Narrative Lead", "keep tone and lore consistent across all writing", "narrative/story_bible.md"), (
            R("writer", "Writer", "write the story bible, quests and in-game text", "narrative/story_bible.md", ("report_exporter",)),
            R("world_builder", "World Builder", "define setting, factions, history and rules of the world", "narrative/world.md", ("report_exporter",)),
            R("dialogue_writer", "Dialogue Writer", "write character dialogue and barks", "narrative/dialogue.md", ("report_exporter",)),
            R("localization_specialist", "Localisation Specialist", "prepare string tables and translation notes", "narrative/strings.json", ("report_exporter",)),
            R("lore_editor", "Lore Editor", "audit continuity and fix contradictions", "narrative/continuity_report.md", ("report_exporter",)),
        ), artifacts=("narrative/narrative_review.md",)),
        StudioDepartment("art", "Dept C · Art & visual assets", "define the visual language and produce asset specifications", R("art_director", "Art Director", "own the visual style and approve every asset spec", "art/style_guide.md"), (
            R("concept_artist", "Concept Artist", "describe key art and mood boards in generation-ready prompts", "art/concepts.md", ("media_generation", "report_exporter")),
            R("character_artist", "Character Artist", "specify characters, animations and silhouettes", "art/characters.md", ("report_exporter",)),
            R("environment_artist", "Environment Artist", "specify tiles, backgrounds and props", "art/environments.md", ("report_exporter",)),
            R("ui_artist", "UI Artist", "specify icons, fonts and interface components", "art/ui_kit.md", ("report_exporter",)),
            R("technical_artist", "Technical Artist", "define asset budgets, formats and the import pipeline", "art/asset_pipeline.md", ("report_exporter",)),
            R("vfx_artist", "VFX Artist", "specify particle and feedback effects", "art/vfx.md", ("report_exporter",)),
        ), artifacts=("art/art_review.md",)),
        StudioDepartment("audio", "Dept D · Audio & voice", "specify music, sound effects and voice", R("audio_director", "Audio Director", "own the sonic identity and mix targets", "audio/audio_direction.md"), (
            R("composer", "Composer", "outline the score, themes and adaptive music states", "audio/music_plan.md", ("report_exporter",)),
            R("sound_designer", "Sound Designer", "list sound effects with triggers and variations", "audio/sfx_list.md", ("report_exporter",)),
            R("voice_director", "Voice Director", "plan voice casting notes and recording scripts", "audio/voice_plan.md", ("report_exporter",)),
            R("audio_integrator", "Audio Integrator", "define middleware events, buses and mix rules", "audio/integration.md", ("report_exporter",)),
        ), artifacts=("audio/audio_review.md",)),
        StudioDepartment("tech_design", "Dept E · Technical design", "turn designs into engineering specifications", R("lead_programmer", "Lead Programmer", "review technical specs against the architecture", "design/tech_specs.md"), (
            R("gameplay_programmer", "Gameplay Programmer", "specify gameplay systems and their interfaces", "design/gameplay_spec.md", ("report_exporter",)),
            R("engine_specialist", "Engine Specialist", "specify rendering, input and the main loop", "design/engine_spec.md", ("report_exporter",)),
            R("ai_programmer", "AI Programmer", "specify enemy AI and pathfinding", "design/ai_spec.md", ("report_exporter",)),
            R("ui_programmer", "UI Programmer", "specify UI architecture and state handling", "design/ui_spec.md", ("report_exporter",)),
        ), artifacts=("design/tech_review.md",)),
    ),
    wave_two=(
        StudioDepartment(
            "engineering", "Core engineering & code implementation", "implement the game", kind="sandbox",
            artifacts=("src/main.py", "src/gameplay/rules.py", "tests/test_rules.py"),
            instructions="Implement a complete, runnable game core in Python following the design and technical specs from upstream results. Write src/main.py (entry point and loop), src/gameplay/rules.py (pure game rules, no I/O) and tests/test_rules.py (pytest tests of the rules). Create folders as needed.",
            review="Check that the rules are deterministic, tests assert real behaviour and pass, and no file is a stub.",
            verification="test -s src/main.py && test -s src/gameplay/rules.py && python -m pytest -q tests",
        ),
        StudioDepartment(
            "build", "Asset compilation & preview rendering", "compile assets and render previews", kind="sandbox",
            artifacts=("media/spritesheet.png", "qa/evidence/gameplay_preview.png"),
            instructions="Using Pillow, procedurally draw a sprite sheet from the art specs (media/spritesheet.png) and render a gameplay preview frame composed from it (qa/evidence/gameplay_preview.png, at least 640x360). Create folders as needed.",
            review="Open both images with Pillow and confirm size, non-uniform content and that the preview matches the art direction.",
            verification="python -c \"from PIL import Image; Image.open('qa/evidence/gameplay_preview.png').verify(); Image.open('media/spritesheet.png').verify()\"",
            visual_evidence=True,
        ),
    ),
    qa=StudioDepartment("qa", "QA, playtest, security & evidence audit", "verify every deliverable and the rendered evidence", R("qa_lead", "QA Lead", "own the quality gate verdict", "qa/qa_report.md"), (
        R("playtest_analyst", "Playtest Analyst", "run a structured playtest review of the build against the design", "qa/playtest.md", ("report_exporter",)),
        R("performance_analyst", "Performance Analyst", "assess frame budget and memory risks", "qa/performance.md", ("report_exporter",)),
        R("security_engineer", "Security Engineer", "review code for unsafe patterns and secrets", "qa/security.md", ("report_exporter",)),
        R("accessibility_auditor", "Accessibility Auditor", "check contrast, input alternatives and readability", "qa/accessibility.md", ("report_exporter",)),
        R("compliance_reviewer", "Compliance Reviewer", "check licences, content ratings and asset provenance", "qa/compliance.md", ("report_exporter",)),
        R("regression_tester", "Regression Tester", "list regression cases tied to design requirements", "qa/regression.md", ("report_exporter",)),
        R("evidence_auditor", "Evidence Auditor", "verify the artifact registry against files on disk and inspect the rendered preview", "qa/evidence_audit.md", ("report_exporter",)),
    ), artifacts=("qa/qa_report.md",)),
    release=StudioDepartment("release", "Release, packaging & delivery", "package the verified build", R("release_manager", "Release Manager", "assemble the release bundle and manifest", "release/manifest.json"), (
        R("build_engineer", "Build Engineer", "write the build and run instructions", "release/README.md", ("report_exporter",)),
        R("release_notes_writer", "Release Notes Writer", "write player-facing release notes", "release/release_notes.md", ("report_exporter",)),
        R("delivery_coordinator", "Delivery Coordinator", "write the manifest listing every released artifact", "release/manifest.json", ("report_exporter",)),
    ), artifacts=("release/manifest.json",)),
    standard_wave_one=("design", "narrative"), standard_wave_two="engineering",
    path_rules=(PathRuleSpec(pattern="src/gameplay/**", rule="Gameplay rules are pure functions of state and input so they can be unit-tested without rendering."),),
)
