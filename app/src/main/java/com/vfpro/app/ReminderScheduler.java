package com.vfpro.app;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import org.json.JSONArray;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

public final class ReminderScheduler {
    static final String PREFS = "vfpro_reminders";
    static final String DATA = "items";
    static final String CHANNEL = "vfpro_schedule_reminders";
    private ReminderScheduler() {}

    static void ensureChannel(Context context) {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            NotificationChannel channel = new NotificationChannel(CHANNEL, "Visit & Follow-up reminders", NotificationManager.IMPORTANCE_HIGH);
            channel.setDescription("৩০ মিনিট আগে Visit ও Follow-up মনে করিয়ে দেয়");
            nm.createNotificationChannel(channel);
        }
    }

    public static void sync(Context context, String json) {
        try {
            SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String old = prefs.getString(DATA, "[]");
            JSONArray oldItems = new JSONArray(old);
            JSONArray items = new JSONArray(json);
            Set<String> nextKeys = new HashSet<>();
            for (int i=0; i<items.length(); i++) nextKeys.add(items.getJSONObject(i).optString("key"));
            for (int i=0; i<oldItems.length(); i++) {
                JSONObject previous = oldItems.getJSONObject(i);
                String key = previous.optString("key");
                if (!nextKeys.contains(key)) cancel(context, key);
            }
            prefs.edit().putString(DATA, items.toString()).apply();
            ensureChannel(context);
            for (int i=0; i<items.length(); i++) schedule(context, items.getJSONObject(i));
        } catch (Exception ignored) {}
    }

    static void schedule(Context context, JSONObject item) {
        try {
            String key = item.getString("key");
            String at = item.getString("at");
            Date when = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm", Locale.US).parse(at);
            if (when == null) return;
            long trigger = when.getTime() - 30L * 60L * 1000L;
            if (trigger <= System.currentTimeMillis()) { cancel(context, key); return; }
            Intent intent = new Intent(context, ReminderReceiver.class);
            intent.setAction("com.vfpro.app.REMINDER");
            intent.setData(android.net.Uri.parse("vfpro://reminder/" + key));
            intent.putExtra("key", key);
            intent.putExtra("type", item.optString("type"));
            intent.putExtra("client", item.optString("client"));
            intent.putExtra("project", item.optString("project"));
            intent.putExtra("at", at);
            PendingIntent pi = PendingIntent.getBroadcast(context, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
            alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, trigger, pi);
        } catch (Exception ignored) {}
    }

    static void cancel(Context context, String key) {
        Intent intent = new Intent(context, ReminderReceiver.class);
        intent.setAction("com.vfpro.app.REMINDER");
        intent.setData(android.net.Uri.parse("vfpro://reminder/" + key));
        PendingIntent pi = PendingIntent.getBroadcast(context, 0, intent,
            PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE);
        if (pi != null) {
            AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
            alarms.cancel(pi);
            pi.cancel();
        }
    }

    public static void restore(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String json = prefs.getString(DATA, "[]");
        try {
            JSONArray items = new JSONArray(json);
            for (int i=0; i<items.length(); i++) schedule(context, items.getJSONObject(i));
        } catch (Exception ignored) {}
    }
}

class ReminderReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        ReminderScheduler.ensureChannel(context);
        String key = intent.getStringExtra("key");
        String type = intent.getStringExtra("type");
        String client = intent.getStringExtra("client");
        String project = intent.getStringExtra("project");
        String at = intent.getStringExtra("at");
        Intent launch = context.getPackageManager().getLaunchIntentForPackage(context.getPackageName());
        PendingIntent content = PendingIntent.getActivity(context, 0, launch,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String message = (project == null || project.isEmpty() ? "" : project + " • ") +
            (at == null ? "" : at.replace('T', ' '));
        Notification.Builder builder = new Notification.Builder(context)
            .setSmallIcon(com.vfpro.app.R.drawable.ic_launcher)
            .setContentTitle((type == null ? "Reminder" : type) + " in 30 minutes")
            .setContentText((client == null ? "" : client) + (message.isEmpty() ? "" : " • " + message))
            .setStyle(new Notification.BigTextStyle().bigText((client == null ? "" : client) + (message.isEmpty() ? "" : " • " + message)))
            .setAutoCancel(true).setContentIntent(content);
        if (Build.VERSION.SDK_INT >= 26) builder.setChannelId(ReminderScheduler.CHANNEL);
        NotificationManager nm = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        nm.notify(key == null ? (int)System.currentTimeMillis() : key.hashCode(), builder.build());
    }
}

class ReminderBootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) ReminderScheduler.restore(context);
    }
}
