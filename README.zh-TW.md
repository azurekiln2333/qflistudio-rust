# QFLI Rust

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

## 專案定位

本儲存庫是一個獨立的 Flutter 應用程式。

它只服務 Rust，不處理其他語言。

介面與其他 QFLI 應用程式共用核心。

應用程式只提供離線功能。

## 真實功能

編輯器、教學頁與範例頁共用一個核心。

編輯器內的 Rust 分析不執行你的程式。

分析器把未儲存的程式碼寫入暫存專案副本。

它呼叫 `rustc` 的中繼資料模式取得診斷。

Cargo、建置腳本與程序巨集都不會啟動。

分析失敗時給出不可用原因。

它不會把分析失敗顯示為沒有錯誤。

工具頁直接提供 Rust 離線工具。

整數工具處理前綴、後綴與型別邊界。

位元運算先按所選型別轉換。
結果按任意精度計算。

字串工具區分位元組數與 Unicode 純量數。

專案檢查工具只讀中繼資料，不編譯。

桌面端檢查呼叫真實的 `cargo metadata`。

行動端只讀專案裡的 `Cargo.toml`。

`rust run <檔案.rs>` 在編輯器終端與獨立終端都能執行。

桌面執行按鈕按設定入口選擇 Cargo 目標。

入口未註冊時，它用 `rustc` 編譯單一檔案。

長按執行目前已儲存的檔案。

長按不改變設定入口。

桌面終端的 `rustc` 與 `cargo` 是真實命令。

`input.txt` 存在時作為標準輸入。

應用程式內建 166 篇教學與 166 個配對範例。

教學與範例的原始檔位於 `tool/rust_content/topics_*.json`。

應用程式內容目錄是 `assets/content_rust/`。

其中 23 個主題附帶 Cargo 專案檔案。

從範例建立專案時，應用程式展開附帶的專案檔案。

單一檔案匯入只取範例程式碼。

Rust 專案範本會帶上 `Cargo.toml`。

它同時忽略 `target/`。

既有 Rust 目錄保持原樣。
它也能按單一檔案執行。

## 桌面與行動端差異

桌面端要求系統裡有官方 Rust 工具鏈。

`cargo` 與 `rustc` 需要在 `PATH` 上。

桌面端直接啟動真實的編譯器。

行動端依賴封裝好的上游 rustc/Miri 引擎。

Android 與 OHOS 已有原生清單與封裝腳本。

儲存庫提供 iOS 建置與封裝腳本。

iOS 封裝產物與裝置驗證待完成。

行動端不提供編譯器命令列。

行動端會提示改用 `rust run`。

行動端分析經原生通道。

應用程式套件必須包含相符的原生分析擴充。

原生通道停在求值之前。

OHOS 上的實際分析驗證尚未完成。

## 相鄰目錄 qfli_studio_core

這是一個獨立的 Git 儲存庫。

它依賴相鄰的 `qfli_studio_core`。

請把兩個儲存庫檢出到同級目錄。

```text
checkout-parent/
  qfli_studio_core/
  qfli_rust/
```

共享編輯器補丁來自 `../qfli_studio_core/vendor/re_editor`。

`pubspec.yaml` 透過路徑相依接入這兩處。

## 離線 Cargo 限制

Cargo 全程離線執行。

相依套件必須已在快取裡，或是儲存庫內的本機路徑相依。

註冊表登入、發佈與其他線上操作都不可用。

## 安裝與執行

先並排放好 `qfli_studio_core` 與 `qfli_rust`。

在 `qfli_rust` 目錄執行：

```text
flutter pub get
flutter run
```

桌面端還要安裝官方 Rust 工具鏈。

把 `cargo` 與 `rustc` 放進 `PATH`。

桌面分析器可讀取 `QFLI_RUSTC`。

它優先於儲存庫內的固定工具鏈。

此變數不設定程式執行器。

## 內容檢查

教學與範例一一配對，共 166 對。

原始檔改動後執行這些命令：

```text
python scripts/generate_rust_content.py
python scripts/generate_rust_content.py --check
python scripts/verify_rust_content.py --report build/rust-content-verification.json
python -m unittest discover -s scripts -p test_rust_content.py
```

`verify_rust_content.py` 用真實主機編譯器逐課編譯。

它執行每個程式。

它再比對程式輸出與宣告輸出。

它同時離線檢查附帶專案。

缺少編譯器時它會失敗。

只有明確加上 `--structure-only` 才跳過執行。

結構檢查報告不作執行結論。

## 裝置驗證限制

主機檢查不能證明 OHOS 上的執行。

目前儲存庫沒有 OHOS 套件內原始碼執行的證據。

未簽章的 OHOS 建置不能證明安裝或執行成功。

OHOS 實體裝置需要相符的 Rust 簽章設定。

歷史 Android 整合測試只涵蓋代表性案例。

它沒有涵蓋全部目錄。

行動端執行結果仍待補齊。

## 原生元件

見 [native/README.md](native/README.md)。

那裡記錄各平台建置、封裝與 ABI 契約。
