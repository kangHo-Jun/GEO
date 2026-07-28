<?php

/**
 * 第三方服务凭证占位（Mail/Postmark/SES/Resend/Slack 等）。
 */

return [

    /*
    |--------------------------------------------------------------------------
    | Third Party Services
    |--------------------------------------------------------------------------
    |
    | This file is for storing the credentials for third party services such
    | as Mailgun, Postmark, AWS and more. This file provides the de facto
    | location for this type of information, allowing packages to have
    | a conventional file to locate the various service credentials.
    |
    */

    'postmark' => [
        'key' => env('POSTMARK_API_KEY'),
    ],

    'resend' => [
        'key' => env('RESEND_API_KEY'),
    ],

    'ses' => [
        'key' => env('AWS_ACCESS_KEY_ID'),
        'secret' => env('AWS_SECRET_ACCESS_KEY'),
        'region' => env('AWS_DEFAULT_REGION', 'us-east-1'),
    ],

    'slack' => [
        'notifications' => [
            'bot_user_oauth_token' => env('SLACK_BOT_USER_OAUTH_TOKEN'),
            'channel' => env('SLACK_BOT_USER_DEFAULT_CHANNEL'),
        ],
    ],

    'blogger' => [
        'client_id' => env('BLOGGER_OAUTH_CLIENT_ID'),
        'client_secret' => env('BLOGGER_OAUTH_CLIENT_SECRET'),
        'redirect_uri' => env('BLOGGER_OAUTH_REDIRECT_URI'),
        'trust_badge_url' => env('BLOGGER_TRUST_BADGE_URL'),
        'cta_url' => env('BLOGGER_CTA_URL', 'https://web-cadalog-ver10.vercel.app/'),
    ],

    'github_image_host' => [
        'token' => env('GITHUB_IMAGE_HOST_TOKEN'),
        'repo' => env('GITHUB_IMAGE_HOST_REPO', 'kangHo-Jun/Blogger-Automation'),
        'branch' => env('GITHUB_IMAGE_HOST_BRANCH', 'main'),
        'path_prefix' => env('GITHUB_IMAGE_HOST_PATH_PREFIX', 'assets/generated'),
    ],

];
