-- 0012_kr_fonte.sql — KR pode ter fonte automática (calculada do dado real).
-- NULL = valor manual (atual digitado). Ex.: 'fat_yoy_pct', 'ticket_yoy_pct'.

ALTER TABLE okr_kr ADD COLUMN IF NOT EXISTS fonte text;
