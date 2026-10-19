import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.gutcare.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.gutcare.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "API_BASE_URL", "\"https://api.gutcare.invalid/api/v1/\"")
    }

    sourceSets.getByName("main").res.srcDir(layout.buildDirectory.dir("generated/registration-notices/res").get().asFile)

    buildTypes {
        debug {
            val emulatorHttp = providers.gradleProperty("allowEmulatorHttp").orNull != "false"
            val debugUrl = providers.gradleProperty("debugApiBaseUrl").orNull
                ?: "http://10.0.2.2:8000/api/v1/"
            buildConfigField("String", "API_BASE_URL", "\"$debugUrl\"")
            buildConfigField("boolean", "ALLOW_EMULATOR_HTTP", emulatorHttp.toString())
        }
        release {
            buildConfigField("boolean", "ALLOW_EMULATOR_HTTP", "false")
            isMinifyEnabled = false
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
    }

    lint {
        abortOnError = true
        checkReleaseBuilds = true
    }
}

val registrationNoticesArtifact = rootProject.layout.projectDirectory.file("../contracts/consent/registration-notices.json")

val validateRegistrationNotices by tasks.registering {
    inputs.file(registrationNoticesArtifact)
    doLast {
        val file = registrationNoticesArtifact.asFile
        check(file.isFile) { "Registration notice artifact is required: ${file.path}" }
        val bytes = file.readBytes()
        check(!(bytes.size >= 3 && bytes[0] == 0xEF.toByte() && bytes[1] == 0xBB.toByte() && bytes[2] == 0xBF.toByte())) {
            "Registration notice artifact must not contain a UTF-8 BOM"
        }
        check(bytes.none { it == 0x0D.toByte() }) { "Registration notice artifact must use LF line endings only" }
        Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
    }
}

val generateRegistrationNotices by tasks.registering(Copy::class) {
    val source = registrationNoticesArtifact
    dependsOn(validateRegistrationNotices)
    from(source)
    into(layout.buildDirectory.dir("generated/registration-notices/res/raw"))
    rename { "registration_notices.json" }
}

tasks.named("preBuild").configure { dependsOn(generateRegistrationNotices) }

tasks.withType<Test>().configureEach {
    systemProperty("gutcare.registrationNoticesPath", registrationNoticesArtifact.asFile.absolutePath)
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.04.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.12.2")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.navigation:navigation-compose:2.9.6")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("com.squareup.retrofit2:retrofit:3.0.0")
    implementation("com.squareup.retrofit2:converter-moshi:3.0.0")
    implementation("com.squareup.moshi:moshi-kotlin:1.15.2")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
    testImplementation("androidx.arch.core:core-testing:2.2.0")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")

    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test:core:1.7.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test:runner:1.7.0")
}
