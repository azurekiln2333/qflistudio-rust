
import {
  FlutterAbility,
  FlutterEngine,
  MethodChannel,
  MethodCall,
  MethodResult,
} from '@ohos/flutter_ohos';
import { authentication } from '@kit.AccountKit';
import { systemShare } from '@kit.ShareKit';
import { common, Want, ConfigurationConstant } from '@kit.AbilityKit';
import { window, router } from '@kit.ArkUI';
import { BusinessError } from '@kit.BasicServicesKit';
import { GeneratedPluginRegistrant } from '../plugins/GeneratedPluginRegistrant';
import { handlePickerCall, isPickerMethod } from './PickerBridge';

const CHANNEL_PLATFORM = 'qflistudio/platform';
const CHANNEL_HUAWEI = 'qflistudio/huawei_account';

export default class EntryAbility extends FlutterAbility {
  onWindowStageCreate(windowStage: window.WindowStage): void {
    // 启动遮罩消失后、Flutter 首帧渲染前，引擎初始化期间窗口会露出
    // 默认白底。窗口底色与 Flutter 的 MD3 surface 保持一致。
    try {
      const isDark = this.context.config?.colorMode ===
        ConfigurationConstant.ColorMode.COLOR_MODE_DARK;
      windowStage.getMainWindowSync().setWindowBackgroundColor(
        isDark ? '#FF111418' : '#FFF8F9FF',
      );
    } catch (e) {
      // 设置失败不影响启动（仅深色模式可能出现短暂白闪）。
    }
    super.onWindowStageCreate(windowStage);
  }

  configureFlutterEngine(flutterEngine: FlutterEngine) {
    super.configureFlutterEngine(flutterEngine)
    GeneratedPluginRegistrant.registerWith(flutterEngine)

    const abilityContext = this.context as common.UIAbilityContext;

    // 通用平台能力：打开系统浏览器（HTML 预览用）。
    const platformChannel = new MethodChannel(
      flutterEngine.dartExecutor.getBinaryMessenger(),
      CHANNEL_PLATFORM,
    );
    platformChannel.setMethodCallHandler({
      onMethodCall(call: MethodCall, result: MethodResult): void {
        if (call.method === 'openAgreement') {
          const url = call.argument('url') as string;
          const title = call.argument('title') as string;
          if (typeof url !== 'string' || !url.startsWith('https://')) {
            result.error('INVALID_URL', '协议地址无效', null);
            return;
          }
          router.pushUrl({ url: 'pages/AgreementReader', params: { url, title } })
            .then(() => result.success(null))
            .catch((err: BusinessError) => result.error('AGREEMENT_OPEN_FAILED', `${err.code}: ${err.message}`, null));
        } else if (call.method === 'openUrl') {
          const url = call.argument('url') as string;
          const want: Want = {
            action: 'ohos.want.action.viewData',
            uri: url,
          };
          abilityContext.startAbility(want)
            .then(() => {
              result.success(null);
            })
            .catch((err: BusinessError) => {
              result.error(`${err.code}`, `${err.message}`, null);
            });
        } else if (call.method === 'shareText') {
          // 系统分享面板（Share Kit）：纯文本分享。
          const title = call.argument('title') as string;
          const text = call.argument('text') as string;
          const record: systemShare.SharedRecord = {
            utd: 'general.plain-text',
            content: text,
            title: title,
          };
          const data = new systemShare.SharedData(record);
          const controller = new systemShare.ShareController(data);
          const options: systemShare.ShareControllerOptions = {};
          controller.show(abilityContext, options)
            .then(() => {
              result.success(null);
            })
            .catch((err: BusinessError) => {
              result.error('SHARE_FAILED', `${err.code}: ${err.message}`, null);
            });
        } else if (isPickerMethod(call.method)) {
          handlePickerCall(abilityContext, call, result);
        } else {
          result.notImplemented();
        }
      },
    });

    // 华为账号（Account Kit v4 / API 11）：
    // AuthorizationWithHuaweiIDRequest -> executeRequest -> authorizationCode，
    // authorizationCode 交给服务端换取 token / userinfo。
    const huaweiChannel = new MethodChannel(
      flutterEngine.dartExecutor.getBinaryMessenger(),
      CHANNEL_HUAWEI,
    );
    huaweiChannel.setMethodCallHandler({
      onMethodCall(call: MethodCall, result: MethodResult): void {
        if (call.method === 'login') {
          try {
            const provider = new authentication.HuaweiIDProvider();
            const request: authentication.AuthorizationWithHuaweiIDRequest =
              provider.createAuthorizationWithHuaweiIDRequest();
            request.scopes = ['openid'];
            request.permissions = [];

            const controller =
              new authentication.AuthenticationController(abilityContext);
            controller.executeRequest(request)
              .then((response: authentication.AuthenticationResponse) => {
                const authResponse =
                  response as authentication.AuthorizationWithHuaweiIDResponse;
                const code: string =
                  authResponse.data?.authorizationCode ?? '';
                if (code.length > 0) {
                  result.success(code);
                } else {
                  result.error('HUAWEI_LOGIN_EMPTY', '未获取到授权码', null);
                }
              })
              .catch((err: BusinessError) => {
                result.error('HUAWEI_LOGIN_FAILED', `${err.code}: ${err.message}`, null);
              });
          } catch (e) {
            const err = e as BusinessError;
            result.error('HUAWEI_LOGIN_ERROR', `${err.code}: ${err.message}`, null);
          }
        } else {
          result.notImplemented();
        }
      },
    });
  }
}
