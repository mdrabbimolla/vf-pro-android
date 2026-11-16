package com.vfpro.app;

import android.Manifest;
import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebChromeClient;
import android.webkit.JsResult;
import android.webkit.JavascriptInterface;
import android.app.AlertDialog;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.graphics.Color;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.ScrollView;
import android.os.Build;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.PrintWriter;
import java.io.StringWriter;

public class MainActivity extends Activity {
    private static final int NOTIFICATION_PERMISSION_REQUEST = 7301;
    private WebView webView;
    private ProgressBar progress;
    private final Handler handler = new Handler(Looper.getMainLooper());

    public class AndroidBridge {
        @JavascriptInterface
        public void syncReminders(String json) {
            ReminderScheduler.sync(MainActivity.this, json);
        }
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(7, 22, 58));
        getWindow().setNavigationBarColor(Color.rgb(7, 22, 58));
        requestNotificationPermission();
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(7, 22, 58));
        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setLoadsImagesAutomatically(true);
        settings.setSupportZoom(false);
        webView.addJavascriptInterface(new AndroidBridge(), "VfAndroid");
        progress = new ProgressBar(this);
        FrameLayout.LayoutParams p = new FrameLayout.LayoutParams(100, 100);
        p.gravity = android.view.Gravity.CENTER;
        root.addView(webView, new FrameLayout.LayoutParams(-1, -1));
        root.addView(progress, p);
        setContentView(root);

        webView.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onJsConfirm(WebView view, String url, String message, JsResult result) {
                new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setPositiveButton("হ্যাঁ", (dialog, which) -> result.confirm())
                    .setNegativeButton("বাতিল", (dialog, which) -> result.cancel())
                    .setOnCancelListener(dialog -> result.cancel())
                    .show();
                return true;
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme() == null ? "" : uri.getScheme();
                if (!scheme.equals("http") && !scheme.equals("https")) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (Exception ignored) {}
                    return true;
                }
                if (uri.getHost() != null && !uri.getHost().equals("127.0.0.1")) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (Exception ignored) {}
                    return true;
                }
                return false;
            }
            @Override public void onPageFinished(WebView view, String url) {
                progress.setVisibility(View.GONE);
                if (url != null && url.startsWith("http://127.0.0.1:5001/")) {
                    view.evaluateJavascript("(function(){fetch('/api/reminders').then(r=>r.ok?r.json():null).then(d=>{if(d&&window.VfAndroid)window.VfAndroid.syncReminders(JSON.stringify(d.items||[]));}).catch(()=>{});})()", null);
                }
            }
        });

        try {
            if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
            Python.getInstance().getModule("server").callAttr("start_server",
                getFilesDir().getAbsolutePath() + "/vfpro_data");
            waitForServer(0);
        } catch (Throwable error) {
            showStartupError(error);
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_PERMISSION_REQUEST);
        }
    }

    private void showStartupError(Throwable error) {
        StringWriter sw = new StringWriter();
        error.printStackTrace(new PrintWriter(sw));
        TextView message = new TextView(this);
        message.setTextColor(Color.WHITE);
        message.setTextSize(13);
        message.setPadding(28, 32, 28, 32);
        message.setText("V&F Pro startup error\n\n" + sw.toString());
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.rgb(7, 22, 58));
        scroll.addView(message);
        setContentView(scroll);
    }

    private void waitForServer(int attempt) {
        if (attempt > 60) {
            progress.setVisibility(View.GONE);
            webView.loadData("<html><body style='font-family:sans-serif;padding:28px;color:#102040'><h2>V&amp;F Pro চালু করা যাচ্ছে না</h2><p>অ্যাপটি বন্ধ করে আবার খুলুন।</p></body></html>", "text/html", "UTF-8");
            return;
        }
        new Thread(() -> {
            boolean ready = false;
            try {
                java.net.HttpURLConnection c = (java.net.HttpURLConnection)
                    new java.net.URL("http://127.0.0.1:5001/").openConnection();
                c.setConnectTimeout(500);
                c.setReadTimeout(500);
                c.getInputStream().close();
                ready = true;
                c.disconnect();
            } catch (Exception ignored) {}
            final boolean ok = ready;
            handler.postDelayed(() -> {
                if (ok) webView.loadUrl("http://127.0.0.1:5001/");
                else waitForServer(attempt + 1);
            }, ok ? 0 : 250);
        }).start();
    }

    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
}
