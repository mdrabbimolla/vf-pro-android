# V&F Pro Android

This Android wrapper packages the supplied V4 Flask application with Chaquopy and an Android WebView.
The Flask service listens only on `127.0.0.1:5001`. SQLite data and the session secret are stored under
the app-private Python HOME directory (`vfpro_data`) and survive ordinary app updates. Uninstalling the
app removes this private data, so export/backup should be added before any production migration.

## Build
Run `gradle assembleDebug` with JDK 17 and Android SDK installed, or use the GitHub Actions workflow.
