# Blue Roux Archive

A static, old-web-style browser for the albums [@blueroux4776](https://www.youtube.com/@blueroux4776) uploads to YouTube,
joined to their Discogs releases, plus a page for each weekly *Gunk In The Groove* radio show.
Rebuilt daily, on a home computer (Option A) or by GitHub Actions to GitHub Pages (Option B).

## Option A: host on your home network (currently used) → http://blueroux.local
Anyone on your wifi can open **http://blueroux.local** (also `http://<this-computer>.local`). It uses nginx on this computer
plus an mDNS name, so there is nothing to configure on the router. Works on macOS, iOS, Linux, Windows 10/11 and recent
Android; if a device can't resolve `.local`, use the IP address instead (`ip -4 addr` on this machine).
The site is only reachable while this computer is on and on the network.

1. `cp .env.example .env`, fill in your keys, `chmod 600 .env`. Set `discogs.username` in `config.yaml`.
2. `sudo ./deploy/setup-local.sh`: installs nginx, publishes the name, opens the firewall **for the home network only** (`LAN_CIDR=… sudo -E ./deploy/setup-local.sh` if your network isn't 192.168.0.0/24).
3. `./deploy/install-timer.sh` (no sudo): daily rebuild at 06:00; if the computer was off it catches up when it's back on.
4. `systemctl --user start --no-block blueroux-update` builds the site right now in the background (without `--no-block` the command waits for the whole job, which can take hours on the first run). Watch progress with `journalctl --user -fu blueroux-update` (Ctrl-C stops watching, not the job). Check the result with `systemctl --user status blueroux-update`.

Tip: in your router's settings, give this computer a **DHCP reservation** so its IP never changes. The `blueroux.local` name
follows IP changes automatically, but a fixed IP makes the fallback address reliable.
Failures ping Discord (if `DISCORD_WEBHOOK_URL` is set); a failed update never replaces the site that's already live.

## Option B: GitHub (private repo to test, then public site)
Keys go in GitHub's encrypted *Secrets*, never in the repo (`.env` is gitignored, and error messages are scrubbed
of key values before they're stored or sent anywhere). `deploy/check-secrets.sh` double-checks before you upload.

**Stage 1: private repo (tests the daily automation; nothing is public)**
1. On github.com: *Settings → Emails* → tick **Keep my email addresses private**. Copy the
   `…@users.noreply.github.com` address shown there, then in this folder:
   `git config user.name "<your GitHub username>"` and `git config user.email "<that noreply address>"`.
2. Install the GitHub CLI and log in: `sudo apt install gh`, then `gh auth login` (GitHub.com → HTTPS → log in with a browser).
3. `deploy/check-secrets.sh`, then `gh repo create blueroux-site --private --source . --push`.
4. Repo *Settings → Secrets and variables → Actions → New repository secret*: `YOUTUBE_API_KEY`, `DISCOGS_TOKEN`
   (same values as `.env`), and later `DISCORD_WEBHOOK_URL`.
5. *Actions → Update site → Run workflow*. When it's green, open the run and download the **site** artifact
   (a zip of the built site). The links in it expect the `/blueroux-site/` prefix, so to browse it:
   `mkdir -p /tmp/t && unzip site.zip -d /tmp/t/blueroux-site && cd /tmp/t && python3 -m http.server`
   → http://localhost:8000/blueroux-site/

**Stage 2: go public**
1. `deploy/check-secrets.sh --history` (checks every past commit too).
2. *Settings → General → Danger Zone → Change visibility → Public*.
3. *Settings → Pages → Source: GitHub Actions*.
4. *Settings → Secrets and variables → Actions → Variables → New repository variable*: `DEPLOY_PAGES` = `true`.
5. Run the workflow. The site appears at `https://<username>.github.io/blueroux-site/`.
6. Turn off the home-network update so the two don't both use the API quotas:
   `systemctl --user disable --now blueroux-update.timer`.

**Git, day to day.** GitHub's daily run commits refreshed data, so run `git pull` before changing anything here.
Then `git add -A && git commit -m "what changed" && git push`. If `git pull` complains about `data/cache` (the
home-network update changed it too), run `git checkout -- data/cache` and pull again: GitHub's copy is just as good. Small edits (overrides, pages) can also be made
straight in GitHub's web editor; the site rebuilds on every push.

## Day to day
| I want to… | Do this |
|---|---|
| Add a page | Drop `pages/something.md` in. Optional front-matter: `title`, `nav_order`, `nav: false`. |
| Fix a wrong/missing video↔release link | Add a line to `overrides/matches.yaml` (see `/status/unmatched.html` on the live site). |
| Confirm a location | Add a line to `overrides/locations.yaml` (see `/status/needs-location.html`). Location suggestions are never shown publicly. |
| Rebuild now | *Actions → Update site → Run workflow*. |

## Local run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd scripts
YOUTUBE_API_KEY=… DISCOGS_TOKEN=… ../.venv/bin/python run_all.py
cd ../dist && python3 -m http.server      # http://localhost:8000
```

## Alerts
- Hard failure (workflow step fails): GitHub emails the repo owner, and Discord is pinged if the webhook is set.
- Soft problems (a source failed so cached data was used, Spinitron layout changed, new unmatched videos): sent to Discord once,
  not repeated daily, and listed on `/status/`.
- A failed update never takes the site down: the last good deploy stays live.

## Credits
Ubuntu Mono © Canonical, Ubuntu Font Licence. Record / cassette / CD illustrations in `static/img/` are original SVGs made for this site.
