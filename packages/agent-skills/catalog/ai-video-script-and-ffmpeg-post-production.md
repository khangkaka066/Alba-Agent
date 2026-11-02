---
name: AI Video Script & FFmpeg Post Production
slug: ai-video-script-and-ffmpeg-post-production
category: media
description: "Practical SOPs, validation checks, and guardrails for ai video script & ffmpeg post production."
trigger_keywords: ["video", "script", "storyboard", "ffmpeg", "subtitle", "audio"]
required_tools: ["media_generation", "report_exporter"]
recommended_models: ["openai/gpt-4.1", "google/gemini-2.5-pro"]
---

## Purpose
Plan a coherent video and produce reproducible edit instructions for narration, visuals, audio, and subtitles.

## Standard operating procedure
1. Confirm audience, platform, duration, aspect ratio, target emotion, brand constraints, and source assets. Build a one-sentence premise and a beginning-middle-end arc.
2. Create a shot-by-shot storyboard with scene duration, framing, action, visual prompt, on-screen text, voiceover, transition, and asset source. Keep shots feasible for the available tools.
3. Check timing by reading narration at realistic speech speed. Leave room for visual comprehension and CTA. Do not overload on-screen text.
4. Prepare a production checklist for asset rights, resolution, frame rate, color consistency, and audio peaks. Record generation prompts and filenames.
5. For FFmpeg, use explicit input order, stream mapping, codecs, pixel format, frame rate, and output dimensions. Preview a short segment before the full render.
6. Apply audio ducking under speech with side-chain compression or measured volume automation. Preserve intelligibility and avoid clipping.
7. Burn subtitles from a reviewed SRT/ASS file, checking timing, safe margins, spelling, speaker labels, and contrast. Inspect the rendered file and capture any technical warnings.

## Checklist
- [ ] Storyboard timing matches requested runtime and platform ratio.
- [ ] Visuals, music, and clips have documented usage rights.
- [ ] Dialogue remains clear over music and peaks do not clip.
- [ ] Subtitle timing and safe-area placement are reviewed.
- [ ] Final codec, dimensions, duration, and audio are checked after export.

## Guardrails
Do not imitate a living creator's distinctive style or use unlicensed copyrighted assets. Do not synthesize a real person's voice or likeness without permission. Avoid misleading edits and label synthetic content when required.

## Output template
### Creative brief
Premise, audience, runtime, and format.

### Storyboard
Timecode, shot, visual, narration, text, transition.

### Post-production recipe
Asset map, FFmpeg commands, ducking, subtitles, and export checks.

### Deliverables
Artifact paths and review notes.

## Golden example
If narration is masked by music, lower the music bed with side-chain compression triggered by the dialogue, audition quiet and loud sections, then inspect subtitle timing against the final rendered audio rather than the draft script.
