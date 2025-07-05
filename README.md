# ScriptsPY

This repository contains utility Python scripts.

## AI Subtitle Auto-Sync for Bazarr

`bazzarPost.py` synchronizes downloaded Arabic subtitles with their embedded English counterparts using a local LLM for semantic matching.

### Usage

```bash
python bazzarPost.py /path/to/video.mkv
```

The script expects `<video>.en.srt` and `<video>.ar.srt` to exist in the same directory. The synced file will be written as `<video>.ar.synced.srt`.

It assumes an OpenAI-compatible model (e.g. phi-4 via LM Studio) is reachable at `http://localhost:1234/v1/chat/completions`.
