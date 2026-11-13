# A tour of the code

For anyone opening this repo for the first time. The rest of `docs/` is reference material, written to be looked up; this page is meant to be read once, top to bottom, and leaves you knowing which few files matter, how a quote gets from a text file to the screen, and how to find your way around the rest.

You don't need to know Python well to follow it. Where a piece of Python is quoted, the sentence around it says what it does.

## The big picture

There are two separate programs in this repo, which share some code:

1. **The factory** (`gutenberg_time_miner.py`, `clean_display_quotes.py`, `quality_filter.py`, `bake_quote_database.py` and friends). It reads Project Gutenberg books, finds sentences that mention a time, cleans and scores them, and writes the result into `idle_hours/assets/quote_database.jsonl`. It's run by hand on a laptop, occasionally, when the quote collection changes. The Pi never runs it. `docs/pipeline.md` describes it.
2. **The clock** (`run_clock.py` and what it calls). It runs on the Pi, forever: every minute it works out the time, picks a quote from that file, draws it and sends the picture to the panel.

If you're trying to understand or change what you see on the panel, you only need the second one. The rest of this tour is about the clock.

## Words this code uses

Most of what makes the code hard to read from outside is its own vocabulary. These are the ones you'll meet everywhere:

| Word | Means |
|---|---|
| **bucket** | A five-minute slot on a 12-hour clock face, like `h2_half_past` (2:28 to 2:32, morning or afternoon). Every quote belongs to one. `buckets.py` defines them |
| **row** | One quote, with its book, author, the time phrase and scores. A Python `dict`: a set of named values like `row["author"]` |
| **corpus** | The whole quote collection. "Raw" is the factory's full output; "baked" is the display-ready version the clock reads |
| **bake** | The factory's last step: take the raw corpus, drop what can't be shown, pre-compute the scores, write `quote_database.jsonl` |
| **`matched_text`** | The time phrase inside a quote ("half past two"), which the renderer draws in the accent colour |
| **`display_quote`** | The cleaned-up quote text as it appears on screen |
| **sidecar** | A small settings file beside the corpus: `selection_overrides.json` (bans and boosts), `content_overrides.json` (hand fixes to quote text) |
| **ledger** / **history** | `history.jsonl`: which quotes were shown recently, so they don't repeat |
| **theme** | A look: colours, fonts and a border or frame. One Python file each, in `idle_hours/render_quote/themes/` |
| **painter** | The function inside a theme file that draws its border or frame |
| **frame** | The final picture, 800×480 pixels |
| **Spectra 6** | The panel's six inks: black, white, red, yellow, blue, green. Every pixel has to be one of them |
| **quiet hours** | The night window where a goodnight frame replaces quotes |
| **fence** | A test whose only job is to fail when two things that must agree drift apart (a doc table and the code, say) |

## Following one quote

Say it's 14:32 on the Pi. Here's the path, with the file and the name of the function at each step. To find a function in a file, search the file for `def` and its name, e.g. `def render(`.

**1. The loop wakes up.** `idle_hours/run_clock.py`, function `main()`. Near the bottom there's a `while not state.stop_requested.is_set():` line: everything indented under it repeats once per minute until the service stops. Each time round it:

- asks `runtime_quiet.compute_quiet` whether it's night; if so it shows the goodnight frame and goes back to sleep;
- asks `runtime_render.current_bucket()` which bucket it is now;
- compares that with the bucket it drew last time. Same bucket, nothing to do. New bucket, draw.

**2. Which bucket?** `idle_hours/buckets.py`, function `bucket_for_time`. It rounds the minute to the nearest five with `((minute + 2) // 5) * 5` (`//` is whole-number division), so 32 becomes 30, and turns 14 into 2 on a 12-hour face. 14:32 is `h2_half_past`.

**3. Asking for a picture.** `idle_hours/runtime_render.py`, function `render_now`. It doesn't draw anything itself. It runs the renderer as a separate program (`subprocess.run([...])`), passing the time, the theme and the file paths as command-line options, and waits for it to finish. A separate program means a crash while drawing can't take the clock down with it. Then, if a display script is configured, it runs that the same way to push the picture to the panel, and logs `Displayed … (N ms)`.

**4. The renderer starts.** `idle_hours/render_quote/core.py`, function `main()`, at the bottom of the file. In order: read the options, `pick_quote(...)` to choose a quote, `render(...)` to draw it, then save the picture to `current.png`. It saves into memory first and writes the file in one go (`atomic_io`), so the panel never reads a half-written picture.

**5. Picking the quote.** `idle_hours/pick_quote.py`. `select_quote` loads the baked corpus, the bans and the recent history, then calls `pick_best`, which:

- takes every row in the bucket;
- drops banned rows and anything shown in the last `history_days`;
- scores the rest and takes the best. If the bucket's empty, it tries the neighbouring buckets.

The scoring is in `score_row`. It returns a list of penalties compared from left to right, so the first one counts most: is it a fragment, is it cleanly cut, how far is its minute from the real time, then the smaller preferences (dialogue, length, quality score, how often that book has appeared). Baked rows carry most of these pre-computed, which is why the clock doesn't have to redo them every minute.

**6. Drawing.** `idle_hours/render_quote/core.py`, function `render`. It:

- looks the theme up. Themes with their own complete design (a train departure board, a split-flap sign) have a **frame** function and draw everything themselves. The rest share one layout and just add a **border**;
- for the shared layout: makes a blank 800×480 picture in the theme's background colour, paints the border, picks a layout for the quote's length (`choose_layout`), then finds the biggest font size at which the quote fits (`fit_quote_balanced`);
- draws the quote with the time phrase in the accent colour, then the author and title.

The colours come from `idle_hours/render_quote/theme_tables.py`, a long list of entries like this one for `dark`:

```python
"dark": {
    "page_bg": SPECTRA6["black"],
    "text": SPECTRA6["white"],
    "accent": SPECTRA6["yellow"],
    ...
},
```

`SPECTRA6` is defined in `palette.py`: the six inks as red-green-blue numbers.

**7. On the panel.** `idle_hours/display_inky.py`, function `main()`. It loads `current.png` and hands it to Pimoroni's `inky` library. A refresh takes about 30 seconds, and it retries a few times if the panel doesn't answer. That's the end of the trip.

## The files that matter

The whole journey above touches about a dozen files. Everything else is support.

| File | One line |
|---|---|
| `idle_hours/run_clock.py` | The loop: wakes every minute, decides whether to draw |
| `idle_hours/runtime_render.py` | Runs the renderer and the display as separate programs; picks random themes |
| `idle_hours/runtime_quiet.py` | Night time: when it starts and ends, and the goodnight frame |
| `idle_hours/runtime_actions.py` | What each button (and each web-page button) does |
| `idle_hours/buckets.py` | Times → buckets |
| `idle_hours/pick_quote.py` | Choosing the quote: bans, history, scores |
| `idle_hours/render_quote/core.py` | Drawing: the main `render` function, the goodnight frame, the source card |
| `idle_hours/render_quote/theme_tables.py` | Every theme's colours and fonts |
| `idle_hours/render_quote/themes/<name>.py` | One theme's border or frame painter |
| `idle_hours/render_quote/furniture.py` | Shared bits of drawing, and the goodnight quote's text (`SLEEP_QUOTE_ROW`) |
| `idle_hours/display_inky.py` | Sending the picture to the panel |
| `idle_hours/assets/config.toml.defaults` | Every setting, with comments |

## What you can skip

Most of the code is in places you'll rarely need:

- **`idle_hours/render_quote/themes/`** is the biggest part of the codebase, and each theme stands alone. You only ever need the one you're looking at.
- **`tests/`** is the test suite, about as big again as the code. It exists to catch mistakes; you can ignore it until a test fails.
- **The factory** (mining, cleaning, quality, baking; see "The big picture").
- **`web_server.py`** and `idle_hours/web/`, the optional curator web page.
- **The rest of the `runtime_*` files**: state, telemetry, the watchdog, locking. They make the clock robust; they don't change what it shows.
- **`render_quote/` below `core.py`** (`layout`, `text`, `fonts`, `primitives`): the machinery `render` calls. Worth a look only if text wraps or sizes oddly.

The layers of checks and tests in this codebase can look alarming. They're there because the code was written mostly by an AI, which rereads everything every time and benefits from tests that catch it drifting. A person can safely read around them.

## Finding things

You'll mostly be searching, not reading. From the repo folder:

```bash
grep -rn "perchance" idle_hours/          # where does this text appear?
grep -rn "def pick_best" idle_hours/      # where is this function defined?
grep -rln "SLEEP_QUOTE_ROW" idle_hours/   # which files use this name?
```

`-r` searches every file in the folder, `-n` shows line numbers, `-l` lists just the file names. In VS Code or another editor, "Find in Files" (Cmd-Shift-F) does the same, and Cmd-clicking a function name jumps to where it's defined.

## Reading a crash

When something goes wrong, Python prints a **traceback**: the chain of function calls that led to the error. On the Pi it's in `journalctl -u idle-hours`. A made-up example (in real life a misspelled theme is caught earlier, with a friendlier message):

```
Traceback (most recent call last):
  File "/home/pi/IdleHours/idle_hours/render_quote/core.py", line 797, in main
    image = render(args.time, quote_row, args.width, args.height, mode=args.mode, theme=args.theme)
  File "/home/pi/IdleHours/idle_hours/render_quote/core.py", line 433, in render
    colors = THEMES[theme]
KeyError: 'newsprnt'
```

Read it **from the bottom up**:

- The last line is the error: a `KeyError` means a name was looked up and isn't there, here a misspelled theme.
- The line above it is the exact code that failed, and the `File … line …` above that says where: `core.py`, line 433, in the function `render`.
- Everything higher up is how the program got there; usually you don't need it.

The error types you'll see most:

| Error | Usually means |
|---|---|
| `KeyError: 'x'` | Looked up `x` and it isn't there: a typo in a name or setting |
| `FileNotFoundError` | A path in the config points at a file that doesn't exist |
| `ModuleNotFoundError: No module named 'x'` | The Python environment is missing something; reinstall it (`MAINTAINING.md`) |
| `PermissionError` / `Read-only file system` | The service isn't allowed to write there |
| `SyntaxError` / `IndentationError` | A hand edit broke the Python. Python cares about indentation: lines in the same block must line up exactly |
| `TypeError`, `AttributeError` | Code given the wrong kind of thing. Usually from a code change, not a setting |

## Making a change

1. **Find the place** with the tables above, or `grep`.
2. **Change one thing.**
3. **Try it** without the panel:

   ```bash
   idle-hours render --time 14:30 --theme dark --output /tmp/test.png
   open /tmp/test.png
   ```

   That runs steps 4–6 of the journey for 2:30 in the `dark` theme and shows you the picture. Pass `--theme` the one you changed.
4. **Undo** if it's wrong: `git diff` shows what you changed, `git checkout -- <file>` puts the original back.

Then run the tests for the area you touched (`pytest tests/test_pick_quote.py`, say; there's one test file per code file, named after it). A failing test tells you what it expected, in plain words, on its last lines, just like a traceback.

`MAINTAINING.md` covers getting a change onto the Pi.

## Where to go next

| To understand | Read |
|---|---|
| Every theme's design, and how to add one | `docs/themes.md` |
| The loop in depth: settings precedence, buttons, quiet hours, what's saved between restarts | `docs/runtime.md` |
| The factory: how quotes are found, cleaned and scored | `docs/pipeline.md` |
| The panel's six colours, and how in-between colours are faked with dots | `docs/spectra6_color_recipes.md` |
| The tests | `docs/testing.md` |
