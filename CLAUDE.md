# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AD Creator — an application for automatic audio description (audiodeskrypcja) generation for videos. It analyzes video content via Google Gemini 2.5, generates timestamped audio description text, synthesizes speech using Google AI TTS, and optionally mixes the audio description with the original video.

## Tech Stack

- **Python** with **Streamlit** for the web UI
- **Google Gemini 2.5** API for video analysis and text generation
- **Google AI TTS** for speech synthesis
- API key expected in system environment variables

## User Flow

1. User pastes a video link (YouTube, Vimeo, cloud storage)
2. User provides context (names, locations, situation description)
3. App generates timestamped audio description text from video + context
4. App synthesizes speech from the description text
5. User can listen to the result
6. Optionally, app mixes audio description with the original video

## Audio Description Rules (Domain Knowledge)

- Place descriptions in gaps without speech/dialogue — music and ambient sounds are acceptable backgrounds
- Descriptions must not overlap with voice (dialogue, narration, etc.)
- Descriptions must be concrete and brief
- Only describe what cannot be inferred from dialogue or sound effects

## Language

The application UI and audio description output are in **Polish**. Code, comments, and commit messages should be in **English**.
