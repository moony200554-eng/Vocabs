-- Run this in Supabase SQL editor (same project: gcjibwxvyerdoyiigjxu)

create table if not exists vocab_users (
    chat_id bigint primary key,
    username text,
    word_index int default 0,
    daily_time text default '09:00',
    timezone_offset int default 330,
    last_sent_date date,
    total_words_sent int default 0,
    created_at timestamp default now()
);
