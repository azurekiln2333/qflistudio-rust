import { router } from '@kit.ArkUI';
import { webview } from '@kit.ArkWeb';
import { hilog } from '@kit.PerformanceAnalysisKit';

interface ReaderParams {
  title: string;
  url: string;
}

@Entry
@Component
struct AgreementReader {
  private controller: webview.WebviewController = new webview.WebviewController();
  @State title: string = '协议';
  @State url: string = 'about:blank';
  @State loading: boolean = true;
  @State error: string = '';

  aboutToAppear(): void {
    const params = router.getParams() as ReaderParams;
    if (params && typeof params.url === 'string' && params.url.startsWith('https://')) {
      this.url = params.url;
      this.title = params.title || '协议';
    } else {
      this.error = '协议地址无效';
      this.loading = false;
    }
  }

  private fail(message: string): void {
    this.loading = false;
    this.error = message;
    hilog.error(0x0000, 'AgreementReader', '%{public}s', message);
  }

  private reload(): void {
    this.error = '';
    this.loading = true;
    try {
      this.controller.loadUrl(this.url);
    } catch (e) {
      this.fail('页面加载失败，请稍后重试');
    }
  }

  build() {
    Column() {
      Row({ space: 12 }) {
        Button() {
          SymbolGlyph($r('sys.symbol.chevron_left')).fontSize(22)
            .fontColor([$r('sys.color.ohos_id_color_text_primary')])
        }
        .type(ButtonType.Normal)
        .width(44)
        .height(44)
        .backgroundColor(Color.Transparent)
        .accessibilityText('返回')
        .onClick(() => router.back())
        Text(this.title)
          .fontSize(20)
          .fontColor($r('sys.color.ohos_id_color_text_primary'))
          .layoutWeight(1)
          .maxLines(1)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
        Button('刷新')
          .type(ButtonType.Normal)
          .backgroundColor(Color.Transparent)
          .onClick(() => this.reload())
      }
      .width('100%')
      .height(56)
      .padding({ left: 8, right: 8 })

      if (this.loading) {
        Progress({ value: 0, total: 100, type: ProgressType.Linear })
          .width('100%')
          .height(3)
          .style({ strokeWidth: 3, enableScanEffect: true })
      }
      Stack() {
        Web({ src: this.url, controller: this.controller })
          .width('100%')
          .height('100%')
          .javaScriptAccess(true)
          .domStorageAccess(true)
          .mixedMode(MixedMode.None)
          .onPageBegin(() => { this.loading = true; this.error = ''; })
          .onPageEnd(() => { this.loading = false; })
          .onErrorReceive((event) => {
            if (event?.request.isMainFrame()) this.fail(`页面加载失败：${event.error.getErrorInfo()}`);
          })
          .onHttpErrorReceive((event) => {
            if (event?.request.isMainFrame()) this.fail(`页面加载失败（HTTP ${event.response.getResponseCode()}）`);
          })
          .onOverrideUrlLoading((request) => {
            const url = request.getRequestUrl();
            return !url.startsWith('https://') && !url.startsWith('http://');
          })
        if (this.error.length > 0) {
          Column({ space: 16 }) {
            Text(this.error).fontSize(16).textAlign(TextAlign.Center)
            Button('重新加载').onClick(() => this.reload())
          }
          .padding(24)
          .width('100%')
          .height('100%')
          .justifyContent(FlexAlign.Center)
          .backgroundColor($r('sys.color.ohos_id_color_background'))
        }
      }
      .width('100%')
      .layoutWeight(1)
    }
    .width('100%')
    .height('100%')
    .backgroundColor($r('sys.color.ohos_id_color_background'))
  }
}
