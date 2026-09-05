package dev.tshimoyama.kumamap

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.KeyEvent
import android.webkit.GeolocationPermissions
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * GitHub Pagesで配信するクマ出没情報マップ(docs/index.html)を表示するだけの薄いWebViewラッパー。
 * MAP_URLが未到達/オフラインの場合は同梱アセット(オフライン時点のスナップショット)にフォールバックする。
 */
class MainActivity : AppCompatActivity() {

    // TODO: GitHub Pages公開後、実際のURLに差し替える (例: https://<user>.github.io/<repo>/)
    private val remoteUrl = "https://REPLACE_ME.github.io/kuma-map/"
    private val localFallbackUrl = "file:///android_asset/index.html"

    private lateinit var webView: WebView
    private var triedRemote = false

    private val locationPermissionLauncher = registerForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission()
    ) { /* 許可結果はWebViewのonGeolocationPermissionsShowPromptで都度判定するため個別処理は不要 */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        webView = WebView(this)
        setContentView(webView)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            setGeolocationEnabled(true)
            cacheMode = WebSettings.LOAD_DEFAULT
        }

        webView.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true && triedRemote) {
                    // リモート取得に失敗した場合のみ、同梱のオフラインスナップショットへフォールバック
                    webView.loadUrl(localFallbackUrl)
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onGeolocationPermissionsShowPrompt(
                origin: String?,
                callback: GeolocationPermissions.Callback?
            ) {
                val granted = ContextCompat.checkSelfPermission(
                    this@MainActivity, Manifest.permission.ACCESS_FINE_LOCATION
                ) == PackageManager.PERMISSION_GRANTED
                callback?.invoke(origin, granted, false)
            }
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED
        ) {
            locationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }

        triedRemote = true
        webView.loadUrl(remoteUrl)
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }
}
