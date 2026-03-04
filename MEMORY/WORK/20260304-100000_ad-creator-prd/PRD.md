---
task: Create detailed PRD for AD Creator application
slug: 20260304-100000_ad-creator-prd
effort: extended
phase: observe
progress: 0/24
mode: interactive
started: 2026-03-04T10:00:00+01:00
updated: 2026-03-04T10:05:00+01:00
---

## Context

Jacek requested a comprehensive PRD for AD Creator — an application that automatically generates audio descriptions (audiodeskrypcja) for video content. The PRD must be detailed enough to plan and build the entire application from scratch.

The app uses Python + Streamlit for UI, Google Gemini 2.5 for video analysis and script generation, Gemini TTS for speech synthesis, and FFmpeg for audio mixing. Target language: Polish. Primary video source: YouTube URLs.

The core engineering challenge identified via first principles: the **time-fitting problem** — descriptions must be meaningful AND fit precisely within detected silence gaps in the original audio track.

### Risks

- Gemini TTS Polish voice quality untested — may need voice selection iteration
- YouTube preview API feature may change — need graceful fallback to File API upload
- Dense dialogue videos may have insufficient gaps — need extended AD support or clear user feedback
- TTS duration varies unpredictably — post-synthesis validation is mandatory

## Criteria

- [ ] ISC-1: PRD contains complete functional requirements for all pipeline stages
- [ ] ISC-2: PRD specifies video acquisition via YouTube URL with Gemini native support
- [ ] ISC-3: PRD specifies Vimeo and cloud storage URL fallback path
- [ ] ISC-4: PRD defines Gemini 2.5 video analysis prompt strategy for timestamped descriptions
- [ ] ISC-5: PRD defines silence gap detection method using FFmpeg silencedetect
- [ ] ISC-6: PRD defines gap-duration-to-word-count fitting algorithm
- [ ] ISC-7: PRD defines Gemini TTS voice and configuration for Polish narration
- [ ] ISC-8: PRD defines FFmpeg audio mixing approach for AD segments
- [ ] ISC-9: PRD defines Streamlit UI layout with all screens and workflow steps
- [ ] ISC-10: PRD defines user context input mechanism and its role in generation
- [ ] ISC-11: PRD defines script review and edit interface for user
- [ ] ISC-12: PRD defines audio playback and download capabilities
- [ ] ISC-13: PRD defines session state management for multi-step workflow
- [ ] ISC-14: PRD defines progress indicators for long-running operations
- [ ] ISC-15: PRD defines error handling for each failure mode
- [ ] ISC-16: PRD defines data model for AD script segments (timestamps, text, audio)
- [ ] ISC-17: PRD defines Python dependency list and architecture
- [ ] ISC-18: PRD defines environment configuration (API keys, FFmpeg path)
- [ ] ISC-19: PRD defines non-functional requirements (performance, limits, accessibility)
- [ ] ISC-20: PRD contains architectural diagram of the complete system
- [ ] ISC-21: PRD defines SRT/WebVTT export format for the generated script
- [ ] ISC-22: PRD defines post-synthesis TTS duration validation against gap boundaries
- [ ] ISC-23: PRD defines video mixing as optional user-triggered operation
- [ ] ISC-24: PRD defines reset/new-video workflow capability
- [ ] ISC-A-1: Anti: PRD does not contain generic placeholder requirements
- [ ] ISC-A-2: Anti: PRD does not omit technical implementation details
