package com.vfpro.app;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

public class ReminderReceiver extends BroadcastReceiver {
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
