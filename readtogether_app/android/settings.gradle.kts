pluginManagement {
    val flutterSdkPath =
        run {
            val properties = java.util.Properties()
            val localPropertiesFile = file("local.properties")
            if (localPropertiesFile.exists()) {
                localPropertiesFile.inputStream().use { properties.load(it) }
            }

            val configuredFlutterSdkPath =
                properties.getProperty("flutter.sdk")?.takeIf { it.isNotBlank() }
                    ?: System.getenv("FLUTTER_ROOT")?.takeIf { it.isNotBlank() }

            require(configuredFlutterSdkPath != null) {
                "flutter.sdk not set in local.properties and FLUTTER_ROOT is not set"
            }
            configuredFlutterSdkPath
        }

    includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    id("com.android.application") version "8.9.1" apply false
    id("org.jetbrains.kotlin.android") version "2.1.0" apply false
}

include(":app")