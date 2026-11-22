# Editing the site: a beginner's guide

## 1. How the site gets made

You never write HTML. You edit a few **source** files, and a build script turns them into the finished
website in the `dist/` folder:

```
pages/*.md, radio-notes/*.md, images/   ─┐
YouTube + Discogs + radio data            ├─► build script ─► dist/  (the website)
templates/ (page layouts)                ─┘
```

**Never edit anything in `dist/`.** It's deleted and rebuilt from scratch every time, so edits there
vanish on the next update (and `dist/` isn't uploaded to GitHub at all).

You don't run a converter yourself either. Whenever the site is built (the daily update, or GitHub's
run after you upload a change), your Markdown is turned into HTML automatically. To see it
before uploading, use the preview (section 5).

## 2. What to edit for what

| I want to… | Edit this |
|---|---|
| Change the About page | `pages/about.md` |
| Add a new page (e.g. "Links") | Create `pages/links.md`. It appears in the top menu at `/links/` |
| Write a blurb at the top of the Radio page | `radio-notes/intro.md` |
| Write a blurb for one show | Create `radio-notes/2026-11-15.md` (that show's date, `YYYY-MM-DD`) |
| Add a picture | Put the file in `images/`, then reference it from a page (section 4) |
| Fix a wrong video ↔ Discogs link | `overrides/matches.yaml` |
| Set an album's location | `overrides/locations.yaml` |

## 3. Writing pages in Markdown

Each file in `pages/` starts with a small settings block between `---` lines, then the text:

```markdown
---
title: About            # name in the top menu and browser tab
nav_order: 10           # menu position: smaller numbers come first
---

# About Blue Roux

Regular paragraphs are just text. Leave a blank line between paragraphs.

## A smaller heading

**bold**, *italic*, and a [link](https://www.youtube.com/@blueroux4776).

- a bulleted
- list

1. a numbered
2. list

> a quote
```

Add `nav: false` to the settings block to make a page that exists but isn't in the menu.
Radio notes are the same, minus the settings block: just write the text.

A show note only appears once that show exists on the site. You can write it in advance and it
shows up when the show does.

## 4. Pictures

1. Put the picture in the `images/` folder. Use simple names: lowercase, no spaces
   (`blueroux-at-the-station.jpg`, not `IMG 2041 FINAL.JPG`). Keep files under about 1 MB; shrink big
   phone photos first.
2. In any page or radio note, write:

   ```markdown
   ![A short description of the picture](/images/blueroux-at-the-station.jpg)
   ```

   The text in `[ ]` is read aloud by screen readers and shown if the picture can't load.
   Always start the path with `/images/`. The build adjusts it so it works both on `blueroux.local`
   and on GitHub Pages.
3. Optional, to make it smaller: `![Description](/images/photo.jpg){: width="300" }`.
   Pictures never get wider than the page, so phones are fine either way.

## 5. Preview before uploading

```bash
cd ~/blueroux-site
deploy/preview.sh
```

Open **http://localhost:8000**, check your page, and press **Ctrl-C** in the terminal when done.
Edit, run it again, and repeat until it looks right. (This only shows it on your own computer.)

## 6. Git: saving and uploading your changes

### The idea
Your project folder and the GitHub repo are two copies of the same project. Git moves changes between them:

| Command | What it does |
|---|---|
| `git pull` | Download the newest changes from GitHub into your folder |
| `git status` | Show what you've changed since the last commit |
| `git diff` | Show the exact lines you changed |
| `git add <file>` | **Stage**: mark a change to include in the next snapshot |
| `git commit -m "message"` | **Commit**: save the staged changes as a snapshot, with a note. Still only on your computer |
| `git push` | Upload your commits to GitHub |

Staging exists so you can choose what goes into a snapshot. Think of it as putting things in a box
(`add`), labelling and sealing the box (`commit`), then shipping it (`push`).

### The routine, every time

```bash
cd ~/blueroux-site

# 1. Get up to date first: GitHub's daily run saves fresh data to the repo.
git checkout -- data/cache     # throw away this computer's copy of the downloaded data
git pull

# 2. Make your edits, then preview them.
deploy/preview.sh               # Ctrl-C when happy

# 3. See what changed.
git status

# 4. Stage, commit, check for secrets, upload.
git add pages/about.md images/blueroux-at-the-station.jpg
git commit -m "Write the About page and add a photo"
deploy/check-secrets.sh
git push
```

After `git push`, GitHub rebuilds the site by itself within a few minutes (watch it in the repo's
**Actions** tab). While the repo is private, the result is the downloadable **site** zip. Once it's
live, the public site updates.

About step 1: this computer's own daily update also refreshes the files in `data/cache/`, and git
won't download GitHub's copy over yours. Since both copies come from the same sources, it's safe to
throw this one away. Once the site is live and you've turned off the home update, that line stops
mattering.

Tip: `git add -A` stages everything that changed. It's handy, but run `git status` first so you
know what "everything" is.

### When something goes wrong

| Problem | Fix |
|---|---|
| `git pull` says your local changes "would be overwritten" | Commit your own edits first (step 4 without `push`), run `git checkout -- data/cache`, then `git pull` again |
| `git push` is "rejected" | GitHub has commits you don't. Run `git pull`, then `git push` |
| I want to undo my edits to a file (not committed yet) | `git restore pages/about.md` |
| I staged a file by mistake | `git restore --staged <file>` |
| I committed something by mistake, not pushed yet | `git reset --soft HEAD~1` (undoes the commit; your edits stay) |
| A text editor opened and I don't know what to do | You forgot `-m "message"`. Type a message on the first line, save, and close the editor |
| Anything else, or a "conflict" | Stop and ask before trying fixes from the internet |

## 7. Editing on github.com instead (no git needed)

For small changes, you can skip all of the above:

- **Edit text**: open the file in the repo on github.com, click the ✏️ pencil, make the change, click
  **Commit changes…**, and keep "Commit directly to the main branch".
- **Add a picture**: open the `images` folder → **Add file → Upload files** → drag it in → **Commit changes**.

GitHub rebuilds the site the same way. Next time you work on this computer, `git pull` first so your
folder has those changes.
