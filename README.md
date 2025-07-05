# ScriptsPY

This repository contains utility Python scripts.

## AI Subtitle Auto-Sync for Bazarr

`BazzarPost.py` synchronizes Arabic subtitles with their English counterparts using an LLM for semantic matching.

### Usage

```bash
python BazzarPost.py episode.en.srt episode.ar.srt
```

The script requires an OpenAI-compatible endpoint. Set the following environment variables:

- `OPENAI_API_KEY` – API key for the model server.
- `OPENAI_API_BASE` – (optional) base URL if using a local server such as LM Studio.

The output will be saved as `episode.ar.synced.srt` in the same directory.
