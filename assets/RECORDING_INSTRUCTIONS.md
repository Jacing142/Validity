# Demo GIF Recording Instructions

Record a 30-45 second GIF showing the full Validity workflow.

## What to show

1. **Input** (0-5s) — paste the example text into the textarea and click Verify
2. **ThoughtPanel streaming** (5-20s) — watch the right panel fill with live agent events as claims are decomposed, ranked, and queried
3. **HITL modal** (20-30s) — the modal appears with ranked claims; remove one, keep the rest, click Continue
4. **Results** (30-45s) — VerdictPanel renders per-claim verdicts with source tiers and the overall verdict

## Example input text

```
The Earth orbits the Sun once every 365.25 days. The Great Wall of China is
visible from space with the naked eye. Mount Everest is the tallest mountain
in the world at 8,849 metres. NASA was founded in 1958.
```

## Recording tools

| Platform | Tool |
|----------|------|
| macOS | [Kap](https://getkap.co/) — free, exports GIF directly |
| Linux | [Peek](https://github.com/phw/peek) — simple GIF recorder |
| Any | [OBS Studio](https://obsproject.com/) — record MP4, convert with ffmpeg |

## Target specs

- **Resolution:** 1280×720 (crop to the app window)
- **Duration:** 30–45 seconds
- **File size:** Under 5 MB (use Gifski or similar to optimise if needed)
- **Frame rate:** 15–20 fps is enough for a UI demo

## Converting MP4 to GIF (ffmpeg)

```bash
ffmpeg -i demo.mp4 -vf "fps=15,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" demo.gif
```

## Save location

Save the final GIF as `assets/demo.gif` and update the README image link:

```markdown
![Validity demo](assets/demo.gif)
```
