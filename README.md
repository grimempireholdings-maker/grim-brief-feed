# The Grim Brief

Public podcast RSS feed for The Grim Brief, hosted through GitHub Pages.

- Feed: https://grimempireholdings-maker.github.io/grim-brief-feed/feed.xml
- Website: https://grimempireholdings-maker.github.io/grim-brief-feed/
- Original audio and cover source: Muse's public podcast feed.

GitHub Pages deploys the root of `main`. Publish future episodes by updating `feed.xml` and pushing a commit to `main`. Spotify checks the published feed for updates; this repository does not generate episodes or automatically sync Muse's feed.

Keep the existing episode GUIDs stable, and add each new episode with a unique GUID, publication date, audio URL, MIME type, byte length, and duration. Preserve the AI-generated disclosure.

The owner email in the public feed is used for directory ownership verification. Never commit access tokens, passwords, verification codes, or private briefing content.
