# GutCare Android

Native Android app module using Kotlin, Jetpack Compose, Material 3 and Navigation Compose. The
module is intentionally a skeleton; feature routes and API DTOs must follow the frozen product and
OpenAPI contracts. The Android app calls only the business API over HTTPS. It does not connect to
the agent service, databases or object storage.

## Build

Use JDK 17 and Android SDK. On Windows, run `./verify.ps1` from this directory. The script uses
an ASCII drive mapping and temporary Gradle paths so Gradle's test worker can start when the
workspace path or Windows username contains non-ASCII characters. On other platforms, run:

```powershell
./gradlew assembleDebug test lint
```

`compileSdk` and `targetSdk` use stable API 36. Install the Android 36 SDK platform and Build Tools
36.0.0 through Android Studio SDK Manager if they are not already present.

Before wiring authentication, provide a Keystore-backed implementation of `SecureSessionStore`.
Never log credentials or persist them in ordinary preferences. Cleartext API origins are rejected.
