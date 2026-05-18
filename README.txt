BAMSPX Subscription Bot

Required environment variables:
- TELEGRAM_TOKEN
- SUPABASE_URL
- SUPABASE_KEY

Optional:
- CHANNEL_ID
- PUBLIC_CHANNEL_URL
- SUPPORT_URL
- BANK_NAME
- ACCOUNT_NAME
- IBAN

Supabase SQL required before deploy:

alter table subscribers
add column if not exists reminder_3d_sent boolean default false,
add column if not exists reminder_1d_sent boolean default false;

Start command:
python main.py
