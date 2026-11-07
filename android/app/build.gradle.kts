import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

/**
 * The release signing key, when this machine has it.
 *
 * `android/keystore/` is gitignored: an app can only ever be updated by a
 * build signed with the same key, so the key is kept out of the repository and
 * backed up by hand. A checkout without it still builds — `assembleDebug`
 * works as always and `assembleRelease` falls back to unsigned rather than
 * failing, because a missing key should not break CI for everyone else.
 */
val signing: Properties? = rootProject.file("keystore/credentials.properties")
    .takeIf { it.exists() }
    ?.let { file -> Properties().apply { file.inputStream().use { load(it) } } }

android {
    namespace = "org.ekyatra.saathi"
    compileSdk = 37

    defaultConfig {
        applicationId = "org.ekyatra.saathi"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        val apiBase = providers.gradleProperty("apiBase").get()
        buildConfigField("String", "API_BASE", "\"$apiBase\"")
    }

    signingConfigs {
        if (signing != null) {
            create("release") {
                storeFile = rootProject.file(signing.getProperty("storeFile"))
                storePassword = signing.getProperty("storePassword")
                keyAlias = signing.getProperty("keyAlias")
                keyPassword = signing.getProperty("keyPassword")
                //: v2 only, and that is not a choice this file gets to make:
                //: the plugin drops v1 JAR signing at minSdk 24 and above
                //: because v2 already covers every device that can install
                //: this. Asking for v1 here was silently ignored, which is
                //: worth knowing before someone adds it back believing it does
                //: something.
                enableV2Signing = true
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.foundation)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.okhttp)
    implementation(libs.okhttp.sse)

    debugImplementation(libs.androidx.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}
