# V&F Pro

V&F Pro is a mobile-first Visit and Follow-up workspace. The Android build can run locally with its embedded Flask server, including native lead scanning and scheduled reminders. The same Flask app can also be hosted as a secure web app and installed on iPhone or Android from the browser.

## Cloud deployment

A Render blueprint is included in `render.yaml`. It provisions a single-instance Python web service with a persistent disk for the SQLite database. The persistent disk is important: do not deploy this configuration on an ephemeral filesystem or scale it to multiple instances.

1. Import this GitHub repository into Render and deploy the Blueprint.
2. Render creates the service and persistent disk. Wait for the `/healthz` health check to pass.
3. Open the service URL. On first launch, create the Admin account. Keep the URL and Admin credentials private.
4. On iPhone, open the URL in Safari, tap Share, then choose **Add to Home Screen**.
5. On Android, open the same URL in Chrome and use **Install app** / **Add to Home screen**.

The hosted service uses HTTPS-only session cookies and a generated Flask secret. Keep the service private to the intended team and maintain backups of the persistent database.

## Android cloud mode

The Android wrapper supports either the existing on-device database or the hosted web service. To switch it to the shared cloud database after deployment, put the full HTTPS service URL on the first line of:

`app/src/main/assets/cloud_url.txt`

Then build a new APK. Leave the file empty to keep the current local-only Android mode. In cloud mode, the Android native scanner and reminder bridge remain available in the WebView.

## Platform notes

- iPhone uses the installed web app and browser camera upload for English lead-list OCR.
- Android APK uses the native document scanner and Android local notifications.
- Browser/PWA data entry requires an internet connection. Personal records are not cached offline.
- iOS background reminders are not yet equivalent to Android AlarmManager notifications.
- SQLite is configured for one hosted instance with a persistent disk. A future multi-instance deployment should move to PostgreSQL.
