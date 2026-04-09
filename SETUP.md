# Ethics in the News — Setup Guide

This is a step-by-step guide to get the site live on GitHub Pages with automatic daily updates.
Estimated time: ~20 minutes.

---

## What you'll end up with

- A public website at `https://YOUR-USERNAME.github.io/ethics-news/`
- Automatic daily updates every morning (7 AM UTC) via GitHub Actions
- Zero ongoing cost

---

## Step 1 — Get a free Gemini API key

1. Go to **https://aistudio.google.com** and sign in with a Google account.
2. Click **"Get API key"** → **"Create API key"**.
3. Copy the key (it looks like `AIza...`). Keep this tab open — you'll need it in Step 4.

---

## Step 2 — Create a GitHub repository

1. Go to **https://github.com/new**
2. Repository name: `ethics-news`
3. Set visibility to **Public** (required for free GitHub Pages + unlimited Actions minutes)
4. Leave everything else at defaults — **do not** check "Add a README"
5. Click **"Create repository"**

---

## Step 3 — Upload the project files

Open your **Terminal** app (search for "Terminal" in Spotlight).

Run these commands one at a time. Replace `YOUR-USERNAME` with your actual GitHub username:

```bash
# Navigate to the project folder
cd /Users/robertchristensen/Documents/ClaudeCodeProjects_rkc/ethics-news

# Initialize git and connect to your new GitHub repo
git init
git add -A
git commit -m "Initial setup"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/ethics-news.git
git push -u origin main
```

When prompted for credentials:
- **Username**: your GitHub username
- **Password**: use a **Personal Access Token** (not your GitHub password — GitHub disabled password auth).
  - Get one at: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token
  - Check the `repo` scope, set expiration to 1 year, click Generate.
  - Copy and paste the token as your password.

---

## Step 4 — Add your Gemini API key as a GitHub secret

1. Go to your repo on GitHub: `https://github.com/YOUR-USERNAME/ethics-news`
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"**
4. Name: `GEMINI_API_KEY`
5. Value: paste your key from Step 1
6. Click **"Add secret"**

---

## Step 5 — Enable GitHub Pages

1. In your repo, go to **Settings** → **Pages** (left sidebar)
2. Under "Source", select **Deploy from a branch**
3. Branch: **main**, folder: **/ (root)**
4. Click **Save**

Your site will be live in ~1 minute at `https://YOUR-USERNAME.github.io/ethics-news/`

---

## Step 6 — Run the first update manually

The automatic schedule runs at 7 AM UTC. To populate the site immediately:

1. In your repo, click the **Actions** tab
2. Click **"Daily Ethics News Update"** in the left sidebar
3. Click **"Run workflow"** → **"Run workflow"**
4. Wait ~2-3 minutes for it to finish
5. Refresh your site

---

## Ongoing maintenance

| Task | How |
|---|---|
| Change update time | Edit `.github/workflows/daily-update.yml`, line `cron: '0 7 * * *'` |
| Rebuild site without fetching | Run `python scripts/generate_html.py` locally, push |
| View fetch/classify logs | GitHub → Actions → click on any workflow run |
| Add more sources/queries | Edit `QUERIES` dict in `scripts/fetch_and_classify.py` |

---

## Troubleshooting

**GitHub Actions failing?**
- Check the Actions tab for error logs.
- Most common cause: `GEMINI_API_KEY` secret not set correctly (Step 4).

**Site shows "No stories yet" after first run?**
- GDELT occasionally has gaps. Try triggering the workflow again the next day.
- Check the Actions log — the script prints how many articles it found.

**Push rejected?**
- Make sure you're using a Personal Access Token, not your GitHub password.

---

## File reference

```
ethics-news/
├── .github/workflows/daily-update.yml  ← automation schedule
├── scripts/
│   ├── fetch_and_classify.py           ← queries GDELT + classifies with Gemini
│   └── generate_html.py                ← builds HTML from JSON data
├── assets/
│   ├── style.css                       ← visual design
│   └── script.js                       ← US/International filter buttons
├── data/
│   ├── articles.json                   ← active articles (last 30 days)
│   └── archive/                        ← monthly JSON archives
├── archive/                            ← monthly HTML archive pages
├── index.html                          ← main page (regenerated daily)
└── requirements.txt
```
