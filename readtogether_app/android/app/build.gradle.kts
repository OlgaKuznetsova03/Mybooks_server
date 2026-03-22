import org.gradle.api.GradleException
import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystorePropertiesFile.inputStream().use(keystoreProperties::load)
}

fun propertyOrEnv(propertyName: String, envName: String): String? {
    val propertyValue = keystoreProperties.getProperty(propertyName)?.trim()?.takeIf { it.isNotEmpty() }
    if (propertyValue != null) {
        return propertyValue
    }

    return System.getenv(envName)?.trim()?.takeIf { it.isNotEmpty() }
}

val releaseStoreFilePath = propertyOrEnv("storeFile", "ANDROID_KEYSTORE_PATH")
val releaseStorePassword = propertyOrEnv("storePassword", "ANDROID_KEYSTORE_PASSWORD")
val releaseKeyAlias = propertyOrEnv("keyAlias", "ANDROID_KEY_ALIAS")
val releaseKeyPassword = propertyOrEnv("keyPassword", "ANDROID_KEY_PASSWORD")

val hasReleaseSigningConfig = listOf(
    releaseStoreFilePath,
    releaseStorePassword,
    releaseKeyAlias,
    releaseKeyPassword,
).all { !it.isNullOrBlank() }

fun requireReleaseSigningConfig() {
    val missingItems = buildList {
        if (releaseStoreFilePath.isNullOrBlank()) add("storeFile / ANDROID_KEYSTORE_PATH")
        if (releaseStorePassword.isNullOrBlank()) add("storePassword / ANDROID_KEYSTORE_PASSWORD")
        if (releaseKeyAlias.isNullOrBlank()) add("keyAlias / ANDROID_KEY_ALIAS")
        if (releaseKeyPassword.isNullOrBlank()) add("keyPassword / ANDROID_KEY_PASSWORD")
    }

    if (missingItems.isNotEmpty()) {
        throw GradleException(
            "Release signing is not configured. Add android/key.properties or CI env vars: ${missingItems.joinToString()}",
        )
    }

    val keystoreFile = file(requireNotNull(releaseStoreFilePath))
    if (!keystoreFile.exists()) {
        throw GradleException("Release keystore file was not found: ${keystoreFile.path}")
    }
}

gradle.taskGraph.whenReady {
    val requiresReleaseSigning = allTasks.any { task ->
        val taskName = task.name.lowercase()
        taskName.contains("release") || taskName.contains("bundle")
    }

    if (requiresReleaseSigning) {
        requireReleaseSigningConfig()
    }
}

android {
    namespace = "com.example.readtogether_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_11.toString()
    }

    signingConfigs {
        if (hasReleaseSigningConfig) {
            create("release") {
                storeFile = file(requireNotNull(releaseStoreFilePath))
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
                enableV1Signing = true
                enableV2Signing = true
            }
        }
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.readtogether_app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            if (hasReleaseSigningConfig) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }
}

flutter {
    source = "../.."
}