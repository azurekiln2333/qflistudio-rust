import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    guard let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "QfliRuntime") else {
      return
    }
    let channel = FlutterMethodChannel(
      name: "qflistudio/runtime", binaryMessenger: registrar.messenger())
    channel.setMethodCallHandler { call, result in
      if call.method == "getRuntimeLibraryDirectory" {
        result(Bundle.main.privateFrameworksPath)
      } else {
        result(FlutterMethodNotImplemented)
      }
    }
  }
}
