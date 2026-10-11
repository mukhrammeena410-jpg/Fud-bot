# hathixfud bot

This package contains the single-bot APK protection service branded as
**hathixfud bot**. The multi-bot/white-label clone system has been removed.

## Configuration

1. Copy `.env.example` to `.env` on the server.
2. Set `BOT_TOKEN` only in the server-side `.env`; no token is bundled here.
3. The owner ID is `8722759285`, the admin/payment contact is `@HATHI02`,
   and force-join is configured for `https://t.me/hathixshadow`.
4. Start with `./start.sh` from the deployment directory.

The admin panel includes user management, analytics, server status, premium
grant/revoke, pricing, bot branding, force-join visibility, broadcasts,
direct messages, promo codes, admin roles, and blacklist controls.

During the upload flow, users only provide the app name and an optional icon.
When they send `/skip`, the bot extracts the best available raster launcher
icon from the uploaded APK automatically; if the APK has only adaptive-icon
XML with no raster variant, it falls back to the safe wrapper icon.