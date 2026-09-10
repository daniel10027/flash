import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("dev.flutter.flutter-gradle-plugin")
}

// MOB-039 — signature release lue depuis android/key.properties (git-ignoré) ou
// depuis les variables d'environnement du CI (FLASH_KEYSTORE_*).
val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}
val hasReleaseSigning =
    System.getenv("FLASH_KEYSTORE_PATH") != null || keystorePropertiesFile.exists()

android {
    namespace = "ci.flash.flash_app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "ci.flash.flash_app"
        minSdk = maxOf(flutter.minSdkVersion, 23) // biométrie + secure storage
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        create("release") {
            if (System.getenv("FLASH_KEYSTORE_PATH") != null) {
                storeFile = file(System.getenv("FLASH_KEYSTORE_PATH"))
                storePassword = System.getenv("FLASH_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("FLASH_KEY_ALIAS")
                keyPassword = System.getenv("FLASH_KEY_PASSWORD")
            } else if (keystorePropertiesFile.exists()) {
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (hasReleaseSigning) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    // MOB-038 — flavors : dev / staging / prod (suffixes d'applicationId + libellés).
    flavorDimensions += "env"
    productFlavors {
        create("dev") {
            dimension = "env"
            applicationIdSuffix = ".dev"
            manifestPlaceholders["appLabel"] = "Flash dev"
        }
        create("staging") {
            dimension = "env"
            applicationIdSuffix = ".staging"
            manifestPlaceholders["appLabel"] = "Flash staging"
        }
        create("prod") {
            dimension = "env"
            manifestPlaceholders["appLabel"] = "Flash"
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
