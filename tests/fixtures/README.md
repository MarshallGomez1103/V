# Synthetic media fixtures

The six files in `media/` contain the same 440 Hz mathematical sine wave:
0.25 seconds, one channel, generated at 16 kHz. They contain no speech,
personal data, or third-party recording.

## Provenance and license

VOZ contributors generated these fixtures locally with FFmpeg's `sine` source.
They are original project test data and are distributed under the repository's
MIT license. No external media was downloaded or adapted.

The committed bytes were produced with FFmpeg 8.1.2 using the commands below.
`+bitexact` and removal of metadata make repeated runs deterministic with the
same FFmpeg build.

```bash
SOURCE='sine=frequency=440:sample_rate=16000:duration=0.25'

ffmpeg -hide_banner -loglevel error -f lavfi -i "$SOURCE" -map 0:a:0 -ac 1 -ar 16000 -fflags +bitexact -flags:a +bitexact -map_metadata -1 -c:a pcm_s16le synthetic-tone.wav
ffmpeg -hide_banner -loglevel error -f lavfi -i "$SOURCE" -map 0:a:0 -ac 1 -ar 16000 -fflags +bitexact -flags:a +bitexact -map_metadata -1 -c:a libmp3lame -b:a 32k -write_xing 0 -id3v2_version 0 synthetic-tone.mp3
ffmpeg -hide_banner -loglevel error -f lavfi -i "$SOURCE" -map 0:a:0 -ac 1 -ar 16000 -fflags +bitexact -flags:a +bitexact -map_metadata -1 -c:a aac -b:a 32k -movflags +faststart synthetic-tone.m4a
ffmpeg -hide_banner -loglevel error -f lavfi -i "$SOURCE" -map 0:a:0 -ac 1 -ar 16000 -fflags +bitexact -flags:a +bitexact -map_metadata -1 -c:a libvorbis -q:a 0 synthetic-tone.ogg
ffmpeg -hide_banner -loglevel error -f lavfi -i "$SOURCE" -map 0:a:0 -ac 1 -ar 16000 -fflags +bitexact -flags:a +bitexact -map_metadata -1 -c:a libopus -b:a 24k synthetic-tone.opus
ffmpeg -hide_banner -loglevel error -f lavfi -i "$SOURCE" -map 0:a:0 -ac 1 -ar 16000 -fflags +bitexact -flags:a +bitexact -map_metadata -1 -c:a libopus -b:a 24k synthetic-tone.webm
```

Opus is decoded at its fixed 48 kHz codec clock even though the input source is
generated at 16 kHz. This is expected behavior for both `.opus` and WebM.

## Integrity manifest

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `synthetic-tone.wav` | 8,044 | `d959e7258ec4ad502f79a133bee06ccfcd2eac7e7c4ef5040c4829f8c29915ee` |
| `synthetic-tone.mp3` | 1,296 | `8ca7afa2af2e68dde5d8a97abb6a86aef7bc210b040763835cd28df7d5ab0b7d` |
| `synthetic-tone.m4a` | 2,290 | `860592365328e72edc49fb5930b76246437fd121efc78a9fc421bd927217fab3` |
| `synthetic-tone.ogg` | 3,622 | `d9d96e65b0fb292a53868f6a412dcc4ade47e30586bae10822802263823017fd` |
| `synthetic-tone.opus` | 867 | `3255e94afd95eb8fd68d7072a8d4386db400cd0b776f8d55428a4746227186f7` |
| `synthetic-tone.webm` | 1,264 | `b673d57f775551995b9d7519c4c0d31372567e5b6c25ce70abbdc69c517cd063` |
