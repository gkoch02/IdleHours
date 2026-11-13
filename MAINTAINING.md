# Keeping Idle Hours running

A guide to running an Idle Hours panel day to day, with nothing but a terminal and a text editor: checking the clock is healthy, changing its settings, getting rid of quotes you don't like, updating, recovering when something breaks, and making small code changes safely.

The rest of the docs (`README.md`, `docs/`) are the full reference. This page only tells you which of it you need, and when.

## What's where

The panel is a Raspberry Pi running one background service called `idle-hours`. Every minute it picks a quote for the time, draws it as a picture and sends it to the screen.

| Thing | Where on the Pi | Touch it? |
|---|---|---|
| The code (a copy of this GitHub repo) | `~/IdleHours` | Only through `git pull`, or small tweaks (see the last section) |
| Its Python environment | `~/.virtualenvs/pimoroni` | Rebuild it if it breaks (see "Things that will break eventually") |
| **Your settings** | `/var/lib/idle-hours/config.toml` | Yes, this is the file you edit |
| Your bans, history and current state | `/var/lib/idle-hours/` (`state.json`, `history.jsonl`) | No; the buttons and the web page manage them |
| Daily logs of what the clock did | `/var/lib/idle-hours/telemetry-YYYYMMDD.jsonl` | Read only, through `idle-hours health` |
| The service definition | `/etc/systemd/system/idle-hours.service` | Rarely; only when rebuilding |

Everything below starts with logging in to the Pi from your Mac: `ssh pi@<the Pi's name or address>`, or the shortcut you set up in `~/.ssh/config`.

## Is it OK?

```bash
systemctl status --no-pager idle-hours
```

`Active: active (running)` is good. Anything else, see "When it stops working".

```bash
cd /var/lib/idle-hours
~/.virtualenvs/pimoroni/bin/idle-hours health --hours 24 --telemetry-path /var/lib/idle-hours/telemetry.jsonl
```

This summarises the last day: how many times it redrew, how many errors, when it last drew. It checks the time every minute (the heartbeats) but only redraws when the time moves into the next five-minute slot, and sometimes not even then, if the quote would be the same. So roughly one render every five minutes while awake (about 190 a day with quiet hours of 22:00–06:00) and zero errors is normal. Each screen refresh takes 20–30 seconds; that's the e-ink panel, not a fault.

To watch what it's doing live (Ctrl-C to stop watching; the clock keeps running):

```bash
journalctl -u idle-hours -f
```

## Changing settings (no code)

All the everyday choices live in one file. The recipe is always the same:

```bash
sudo cp /var/lib/idle-hours/config.toml /var/lib/idle-hours/config.toml.bak-$(date +%Y%m%d)   # 1. back it up
sudoedit /var/lib/idle-hours/config.toml                                                        # 2. edit
~/.virtualenvs/pimoroni/bin/python -c 'import tomllib; tomllib.load(open("/var/lib/idle-hours/config.toml", "rb")); print("config OK")'   # 3. check it
sudo systemctl restart idle-hours                                                               # 4. restart
systemctl status --no-pager idle-hours                                                          # 5. check it's running
```

Step 3 prints `config OK`, or an error naming the line that's broken. Don't restart until it says OK (see "If you make a typo" below for why).

The settings you're most likely to want:

| Setting | What it does | Example |
|---|---|---|
| `theme` | The look. A theme name, `random` (a new one each time), or `auto` (one theme by day, another by night) | `theme = "random"` |
| `auto_day_theme`, `auto_night_theme` | The two themes `auto` switches between | `auto_day_theme = "newsprint"` |
| `quiet_start`, `quiet_end` | When the panel sleeps and shows the goodnight frame instead of quotes | `quiet_start = "23:00"` |
| `quiet_off` | `true` to show quotes all night | `quiet_off = false` |
| `quiet_theme` | The theme for the goodnight frame: `inherit`, `random`, or a name | `quiet_theme = "random"` |
| `history_days` | How many days before a quote may repeat | `history_days = 7` |
| `interval_seconds` | How often it checks the time. Leave at 60 | `interval_seconds = 60` |

Rules for the file: text goes in "double quotes", `true`/`false` and numbers don't, and a line starting with `#` is ignored. For the list of theme names, run `~/.virtualenvs/pimoroni/bin/idle-hours render --help` and look at `--theme`. `idle_hours/assets/config.toml.defaults` in the repo lists every setting with a comment.

**If you make a typo**, what happens depends on the kind:

- **A broken file** (a missing closing quote, a stray character): the clock can't read any of it, so it throws the whole file away and starts with its built-in defaults. Those don't know where the screen driver is or where your settings and bans live, so the panel stops updating. Step 3 catches this before it happens; if it's already happened, restore your backup (below).
- **A readable file with one bad setting** (a misspelled name, a theme that doesn't exist, a time like `25:00`): the clock ignores just that setting, keeps the rest, and logs a warning. So if a change seems to have no effect, look in the log for the word `config`:

```bash
journalctl -u idle-hours --since "10 minutes ago" | grep -i config
```

**To undo**, copy your backup back and restart:

```bash
sudo cp /var/lib/idle-hours/config.toml.bak-YYYYMMDD /var/lib/idle-hours/config.toml
sudo systemctl restart idle-hours
```

## The buttons

The four buttons on the side of the panel, short press / hold for 2 seconds:

| Button | Press | Hold |
|---|---|---|
| A | Same quote, another theme | Never show this theme again |
| B | Another quote | Never show this quote again |
| C | Show where the quote is from | Undo the last "never again" |
| D | Sleep now / wake up | Shut the Pi down safely |

Hold **D** before unplugging the Pi. Pulling the power while it's writing can corrupt the SD card, which is the most common way a Pi dies.

## Quotes you don't like

Hold **B** while the quote is on screen. That's the whole job.

The bans are written to a file called `selection_overrides.json`. Where that file lives decides whether your bans are safe during updates, so check your config for an `overrides` line:

- `overrides = "/var/lib/idle-hours/selection_overrides.json"`: good. Your bans live beside your settings, updates never touch them, and the backup below includes them.
- No `overrides` line: the bans are meant to go into the copy inside `~/IdleHours`, the code folder, but the service is locked out of writing to your home folder, so holding B fails (the log shows a "read-only file system" error). The clock says so in the log each time it starts, with a line ending `quote bans will fail to save` that names the setting to add. Fix it once by adding the line above, and `content_overrides = "/var/lib/idle-hours/content_overrides.json"` under it, to your config (see "Changing settings"), then restart. On that start the clock copies the shipped files across, so nothing is lost, and the warning goes away. The shipped `config.toml.example` already has both lines; configs made from `config.toml.defaults` don't.

For anything more (looking up a quote, lifting theme bans, browsing what it's shown this week), there's a web page on the Pi. It's off unless your config has this line, so add it first if it's missing (see "Changing settings"):

```toml
web_bind = "127.0.0.1:8080"
```

It only listens to the Pi itself, so reach it through an SSH tunnel from your Mac:

```bash
ssh -L 8080:127.0.0.1:8080 pi@<the Pi>
```

Leave that window open and visit <http://127.0.0.1:8080> on the Mac. Close the window when you're done.

## Updating

```bash
cd ~/IdleHours
git pull --ff-only origin main
sudo systemctl restart idle-hours
systemctl status --no-pager idle-hours
```

If the update changed `pyproject.toml` (the list of things the code needs), also run this before the restart:

```bash
~/.virtualenvs/pimoroni/bin/pip install -e '.[pi]'
```

**To go back to the version that worked**, every release has a tag (`v3.1.0`, `v3.2.0`, …; the list is in `CHANGELOG.md` and on the GitHub releases page):

```bash
cd ~/IdleHours
git fetch --tags origin
git checkout v3.1.0
sudo systemctl restart idle-hours
```

(The `fetch --tags` matters: the Pi's copy only follows `main`, so it doesn't have the tags until you ask for them.)

`git checkout main` and `git pull` put you back on the latest.

## When it stops working

| What you see | Try |
|---|---|
| Screen frozen on an old quote | `systemctl status idle-hours`. If it's not running, `sudo systemctl restart idle-hours`, then `journalctl -u idle-hours -n 50` for the reason |
| Service keeps failing right after a settings change | Restore your config backup (above) |
| Service keeps failing right after an update | Go back to the previous tag (above) |
| Fails after a Pi system update | See "Things that will break eventually" |
| Buttons do nothing | Restart the service. If still dead, `~/.virtualenvs/pimoroni/bin/idle-hours probe-buttons` shows whether the Pi sees the presses |
| Times are an hour off | The Pi's time zone: `timedatectl` shows it, `sudo timedatectl set-timezone America/Los_Angeles` (your zone) fixes it |
| Can't log in to the Pi | Its network address changed; your router's device list shows the new one. Update `~/.ssh/config` on the Mac |
| Pi won't boot at all | Probably the SD card. See "Rebuilding from scratch" |

The log nearly always says what's wrong in its last lines. Even without understanding Python, the last line before `Traceback` or `Error` usually names the file or setting at fault.

## Back up now, while it works

Copy your settings and anything you added to the Pi onto the Mac, from a Mac terminal:

```bash
mkdir -p ~/Backups/idle-hours
rsync -a --exclude 'telemetry-*' 'pi@<the Pi>:/var/lib/idle-hours/' ~/Backups/idle-hours/
```

That copies your settings (and your config backups), your theme bans (`state.json`), the quote history, any photos you added, and your quote bans if your config has the `overrides` line described under "Quotes you don't like". It skips the daily logs, which you won't need. Run it again whenever you change something; it only copies what's changed.

## Rebuilding from scratch

For a dead SD card or a new Pi. Allow an hour.

1. Flash Raspberry Pi OS Lite (64-bit) onto a card with Raspberry Pi Imager on the Mac. In its settings, set the username to `pi`, your Wi-Fi, and turn on SSH.
2. Log in, then:

   ```bash
   sudo apt update && sudo apt install -y git
   git clone https://github.com/gkoch02/IdleHours.git ~/IdleHours
   cd ~/IdleHours
   ./scripts/bootstrap_pi_inky.sh
   sudo reboot
   ```

3. Log in again and finish:

   ```bash
   cd ~/IdleHours
   CONTINUE_AFTER_REBOOT=1 ./scripts/bootstrap_pi_inky.sh
   ```

   It ends by drawing a test quote on the panel. If it does, the hard part works.

4. Put your backup back before the service first starts, so it finds your settings, bans and history instead of seeding fresh ones. On the Pi:

   ```bash
   sudo install -d -o pi -g pi -m 0750 /var/lib/idle-hours
   ```

   Then from the Mac:

   ```bash
   rsync -a ~/Backups/idle-hours/ 'pi@<the Pi>:/var/lib/idle-hours/'
   ```

   That restores everything the backup holds (settings, theme bans, history, quote bans and fixes, photos), owned by `pi` as the service expects.

5. Install the service and start it, back on the Pi:

   ```bash
   cd ~/IdleHours
   sudo cp ops/idle-hours.service.example /etc/systemd/system/idle-hours.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now idle-hours
   systemctl status --no-pager idle-hours
   ```

   Skip the "copy the example config" step that `README.md` and the bootstrap script mention: your restored `config.toml` replaces it.

`docs/pi_setup_inky_impression.md` has the long version, including what to check when the panel stays blank.

## Things that will break eventually

Left alone, the Pi will run for years. What breaks it is change:

- **A big Raspberry Pi OS upgrade** (a new Debian version) usually brings a new Python, which strands the Python environment. Symptom: the service fails with `No module named` or `python: not found`. Fix: rebuild the environment, then restart:

  ```bash
  rm -rf ~/.virtualenvs/pimoroni
  python3 -m venv --system-site-packages ~/.virtualenvs/pimoroni
  cd ~/IdleHours && ~/.virtualenvs/pimoroni/bin/pip install -e '.[pi]'
  sudo systemctl restart idle-hours
  ```

  Routine `sudo apt update && sudo apt upgrade` is safe; it's the jump between major versions that does this. Simplest of all: don't do major upgrades on an appliance that works.

- **The Pimoroni `inky` library** (the screen driver) changes now and then. If an update makes the screen stop refreshing, pin the version that worked: `~/.virtualenvs/pimoroni/bin/pip install 'inky==2.5.0'` (check `pip list` on a working Pi for the number).

- **The SD card** wears out. A spare card with a working copy, or the backup above, makes this a 20-minute job instead of an afternoon.

Nothing on the panel depends on the internet once it's running: the quotes are all on the Pi. GitHub only matters for updates.

## Small code changes

Settings cover most wishes. When they don't, [`docs/CODE_TOUR.md`](docs/CODE_TOUR.md) explains how the code fits together, and small edits are within reach without knowing Python well, as long as you keep to one change at a time and keep git's safety net.

**The safety net.** On the Pi, in `~/IdleHours`:

- `git status` lists files you've changed.
- `git diff` shows exactly what you changed.
- `git checkout -- <file>` throws your change to that file away and puts the original back.

**Trying a change without touching the panel.** On the Mac, in your copy of the repo, with its Python environment (`source .venv/bin/activate`, or set it up with the "Quick start" in `README.md`):

```bash
idle-hours render --time 14:30 --theme dark --output /tmp/test.png
open /tmp/test.png
```

That draws the 2:30 quote in the `dark` theme to a picture on the Mac. If the picture looks right, the change works.

**Where common things live:**

| To change | Look in |
|---|---|
| The goodnight quote ("To sleep, perchance to dream.") | `SLEEP_QUOTE_ROW` in `idle_hours/render_quote/furniture.py`. `matched_text` is the word drawn in colour and must appear in `display_quote` exactly |
| A theme's colours or fonts | `idle_hours/render_quote/themes/<theme name>.py`; each theme's notes are in `docs/themes.md` |
| A quote's wording | Ban it (hold B) instead; editing the quote files by hand breaks the build |

**Getting it onto the Pi.** The quick way is to make the same edit on the Pi itself (`nano ~/IdleHours/<file>`) and restart the service. It stays until the next `git pull`, which will refuse to run while your edit is there: `git diff > ~/my-change.patch` saves it, `git checkout -- <file>` clears it, and after the pull `git apply ~/my-change.patch` puts it back (if the file hasn't changed underneath it).

The lasting way is to commit it in the repo on GitHub (on a branch, then a pull request, since `main` is protected), and `git pull` on the Pi. The tests on GitHub will tell you if the change broke something; some of them compare pictures pixel by pixel, so any change to how a theme looks fails those on purpose until the reference pictures are updated.

**Leave alone:**

- `idle_hours/assets/quote_database.jsonl` and `candidates-attributed.jsonl`: the quote collection is generated by the corpus pipeline (`docs/pipeline.md`), not edited by hand.
- `/etc/systemd/system/idle-hours.service`: two of its lines must match each other for the buttons to work; see "Install the service" in `README.md`.
- `/boot/firmware/config.txt`: the screen needs the settings the bootstrap script put there.
