# The Grim Brief

Public podcast RSS feed for The Grim Brief, hosted through GitHub Pages.

- Feed: https://grimempireholdings-maker.github.io/grim-brief-feed/feed.xml
- Website: https://grimempireholdings-maker.github.io/grim-brief-feed/
- Original audio and cover source: Muse's public podcast feed.

The **Sync podcast feed** GitHub Actions workflow runs every weekday at **9:30 AM America/New_York**, following daylight-saving changes. It fetches only the existing public Muse feed, appends new episodes to `feed.xml`, and deploys the public site directly to GitHub Pages. Spotify picks up new episodes from the same feed URL already submitted; no resubmission is needed. GitHub scheduling and Spotify ingestion can introduce delays.

Run it on demand from **Actions → Sync podcast feed → Run workflow**. Pushes to the workflow, script, tests, feed or site files also run the workflow. Muse must still generate and publish each episode in the public source feed; this workflow does not create episodes or access the personal briefing.

## Deployment and permissions

GitHub Pages uses **GitHub Actions** as its publishing source. The sync job explicitly requests `contents: write`; the deployment job requests `pages: write` and `id-token: write`. Repository-wide workflow permissions can remain at their read-only default. No personal access token or extra secret is needed.

The workflow stages only `feed.xml`, `index.html`, `cover.jpg` and `.nojekyll` for publication. It deploys in the same run because commits made with `GITHUB_TOKEN` do not trigger branch-based Pages builds. Failed source downloads or validation stop the run before committing or deploying; the previously published feed stays available.

## Episode preservation

Already-published episodes keep their existing GUIDs, titles, dates and metadata. The original premiere URL is mapped to its corrected audio, and matching audio URLs are deduplicated. Episodes remain in the public archive even if they disappear from Muse's source. A repeated sync with no new episodes does not modify `feed.xml`. Edits to an already-published episode can be made directly in this repository.

Keep the existing episode GUIDs stable, and add each new episode with a unique GUID, publication date, audio URL, MIME type, byte length, and duration. Preserve the AI-generated disclosure.

The owner email in the public feed is used for directory ownership verification. Never commit access tokens, passwords, verification codes, or private briefing content.

## Local checks

```sh
python -m unittest discover -s tests -v
python scripts/sync_feed.py --dry-run
```
