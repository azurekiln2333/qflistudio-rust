import groovy.json.JsonSlurper

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val flutterTarget = (project.findProperty("target") as? String)?.replace('\\', '/') ?: ""
val isIntegrationTest = providers.gradleProperty("qfliIntegrationTest").orNull == "true" ||
    flutterTarget.startsWith("integration_test/") ||
    flutterTarget.contains("/integration_test/") ||
    (flutterTarget.contains("/flutter_test_listener.") && flutterTarget.endsWith("/listener.dart"))
val rustAbiMapping = mapOf("android-arm64" to "arm64-v8a", "android-x64" to "x86_64")
val rustPlatforms = (project.findProperty("target-platform") as? String)
    ?.split(",") ?: rustAbiMapping.keys.toList()
val rustAbis = rustPlatforms.map { target ->
    rustAbiMapping[target] ?: throw GradleException("Native Rust supports only android-arm64 and android-x64")
}

android {
    namespace = "com.azurekiln.qfli.rustcore"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = providers.gradleProperty("qfliNdkVersion").orElse("27.0.12077973").get()

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    packaging {
        jniLibs {
            // The interpreter loads its backend by an absolute nativeLibraryDir path.
            useLegacyPackaging = true
            keepDebugSymbols += "**/libqfli_miri.so"
            keepDebugSymbols += "**/librustc_*.so"
            keepDebugSymbols += "**/libstd-*.so"
        }
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.azurekiln.qfli.rustcore" +
            if (isIntegrationTest) ".integrationtest" else ""
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        ndk {
            abiFilters.clear()
            abiFilters += rustAbis
        }
    }

    buildTypes {
        configureEach {
            ndk {
                abiFilters.clear()
                abiFilters += rustAbis
            }
        }
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

val checkAndroidRustRuntime by tasks.registering {
    doLast {
        for (abi in rustAbis) {
            val architecture = if (abi == "x86_64") "x64" else "arm64"
            val manifestFile = rootProject.file("../assets/miri/manifest.android-$architecture.json")
            check(manifestFile.isFile) {
                "Build and package the pinned Android Rust runtime for $abi with scripts/package_miri_runtime.py"
            }
            val manifest = JsonSlurper().parse(manifestFile) as Map<*, *>
            check(manifest["schemaVersion"] == 2 && manifest["platform"] == "android" &&
                manifest["architecture"] == architecture && manifest["rustVersion"] == "1.98.1" &&
                manifest["rustCommit"] == "48a229ceaefd4985c50990b14116b6d856af0985") {
                "Android Rust package identity does not match $abi"
            }
            val libraries = manifest["nativeLibraries"] as List<*>
            check(libraries.any { (it as Map<*, *>)["role"] == "adapter" } &&
                libraries.any { (it as Map<*, *>)["role"] == "backend" }) {
                "Android Rust package requires its adapter and compiler backend"
            }
            for (item in libraries) {
                val entry = item as Map<*, *>
                val library = file("src/main/jniLibs/$abi/${entry["path"]}")
                check(library.isFile && library.length() == (entry["size"] as Number).toLong()) {
                    "Android Rust library is missing or incomplete: $library"
                }
            }
            for (item in manifest["files"] as List<*>) {
                val entry = item as Map<*, *>
                val asset = rootProject.file("../assets/miri/${entry["asset"]}")
                check(asset.isFile && asset.length() == (entry["size"] as Number).toLong()) {
                    "Android Rust guest data is missing or incomplete: $asset"
                }
            }
        }
    }
}
tasks.named("preBuild").configure { dependsOn(checkAndroidRustRuntime) }

flutter {
    source = "../.."
}
