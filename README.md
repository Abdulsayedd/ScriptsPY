# ScriptsPY

This repository contains helper scripts. The `bazzarPost.py` script can
extract embedded English subtitles from a video file using `ffprobe` and
`ffmpeg`. If a `<video>.en.srt` file is missing, it attempts to extract
an English subtitle track from the video and save it automatically.

## Requirements

- Python 3
- `ffmpeg` (provides both `ffprobe` and `ffmpeg` commands)

Ensure `ffmpeg` is installed and available in your `PATH` before running
`bazzarPost.py`.
